"""Ejecución de transiciones de estado del reporte (US-013).

La validación vive acá y no en un serializer: una transición inválida tiene que
ser imposible incluso llamando al modelo directamente desde el shell.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Report
from .models import ReportAreaAssignment
from .models import ReportStatusHistory
from .signals import report_area_assigned
from .signals import report_status_changed
from .state_machine import AREA_REASSIGNMENT_STATUS
from .state_machine import Actor
from .state_machine import Origin
from .state_machine import Transition
from .state_machine import get_transition
from .state_machine import transitions_from

REASON_REQUIRED_MESSAGE = "Esta acción requiere indicar un motivo."
AREA_REQUIRED_MESSAGE = (
    "Esta acción requiere asignar un área operativa responsable."
)
AREA_NOT_ALLOWED_MESSAGE = (
    "Esta acción no recibe un área operativa."
)
SAME_AREA_MESSAGE = "El reporte ya está asignado a esa área operativa."


class TransitionError(Exception):
    """Transición rechazada por la máquina de estados."""

    def __init__(
        self,
        message: str,
        *,
        current_status: str,
        available: tuple[str, ...],
    ):
        super().__init__(message)
        self.message = message
        self.current_status = current_status
        self.available = available


class ReasonRequiredError(TransitionError):
    """La transición exige un motivo y no se recibió ninguno."""


class GuardRejectedError(TransitionError):
    """La transición existe y el estado es el correcto, pero el reporte no la admite.

    Es distinto de una transición inválida: acá el problema no es de dónde está
    el reporte sino de una condición propia suya —hoy, que ya gastó su única
    apelación—. Por eso responde ``409`` y con el motivo que declara la guarda.
    """


class AreaRequiredError(TransitionError):
    """La transición exige un área operativa y no se recibió ninguna (US-028).

    Es un error de la máquina de estados y no una validación del serializer a
    propósito: la garantía que interesa es que **ningún** camino deje un reporte
    En proceso sin responsable operativo, ni siquiera una llamada desde el
    shell.
    """


def _unavailable(report: Report, operation: str, actor: Actor) -> TransitionError:
    available = tuple(t.operation for t in transitions_from(report.status, actor))
    return TransitionError(
        f"No se puede ejecutar «{operation}» sobre un reporte en estado "
        f"«{report.get_status_display()}».",
        current_status=report.status,
        available=available,
    )


def apply_transition(  # noqa: PLR0913 (cada parámetro es un requisito distinto)
    report: Report,
    operation: str,
    *,
    actor: Actor,
    changed_by,
    reason: str = "",
    operational_area=None,
    confirmation_count: int | None = None,
) -> Report:
    """Mueve el reporte de estado y deja el asiento del historial.

    Bloquea la fila con ``select_for_update`` dentro de una transacción, para que
    dos pestañas del panel no puedan ejecutar dos transiciones simultáneas sobre
    el mismo reporte: la segunda encuentra el estado ya cambiado y se rechaza.

    ``operational_area`` es obligatoria en las transiciones marcadas con
    ``requires_area`` —hoy solo ``procesar``— y se rechaza en las demás. El
    cambio de estado y la asignación se escriben en la **misma transacción**:
    un reporte En proceso sin área nunca llega a existir, ni siquiera un
    instante (US-028).
    """
    transition: Transition | None = get_transition(operation)
    if transition is None or transition.actor != actor:
        raise _unavailable(report, operation, actor)

    reason = (reason or "").strip()
    if transition.requires_reason and not reason:
        raise ReasonRequiredError(
            REASON_REQUIRED_MESSAGE,
            current_status=report.status,
            available=(operation,),
        )
    if transition.requires_area and operational_area is None:
        raise AreaRequiredError(
            AREA_REQUIRED_MESSAGE,
            current_status=report.status,
            available=(operation,),
        )
    if operational_area is not None and not transition.requires_area:
        raise TransitionError(
            AREA_NOT_ALLOWED_MESSAGE,
            current_status=report.status,
            available=(operation,),
        )

    assignment = None
    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.status != transition.source:
            raise _unavailable(locked, operation, actor)

        # La guarda se evalúa sobre la fila ya bloqueada, no sobre la copia que
        # recibió la función: entre una y otra pudo entrar una apelación.
        if transition.guard is not None:
            rejection = transition.guard(locked)
            if rejection is not None:
                raise GuardRejectedError(
                    rejection,
                    current_status=locked.status,
                    available=(),
                )

        previous_status = locked.status
        locked.status = transition.target
        changed_fields = ["status", "updated_at"]

        if operational_area is not None:
            assignment = _assign_area(
                locked,
                operational_area,
                assigned_by=changed_by,
            )
            changed_fields += ["operational_area", "area_assigned_at"]

        # Los sellos acompañan al estado y se escriben en el mismo ``save()``:
        # un reporte con el estado nuevo y sin su fecha no llega a existir.
        now = timezone.now()
        if transition.target == Report.Status.ARCHIVADO:
            # El listado de "mis reportes" muestra la fecha y no trae el
            # historial del que deducirla.
            locked.archived_at = now
            changed_fields.append("archived_at")
        if transition.origin is Origin.CIERRE_OPERARIO:
            # Desde acá corre la ventana de objeción de US-047, y esta es la
            # fecha que toma el indicador de tiempo de resolución de US-023.
            locked.closed_at = now
            locked.objection_warning_sent_at = None
            changed_fields += ["closed_at", "objection_warning_sent_at"]
        if transition.origin is Origin.APELACION_CIUDADANO:
            # El contador se incrementa dentro de la transacción y sobre la fila
            # bloqueada: es lo que hace confiable la guarda del tope.
            locked.appeal_count += 1
            changed_fields.append("appeal_count")

        locked.save(update_fields=changed_fields)

        history = ReportStatusHistory.objects.create(
            report=locked,
            status=transition.target,
            previous_status=previous_status,
            changed_by=changed_by,
            reason=reason,
            # El origen sale de la tabla, no de quien invoca.
            origin=transition.origin,
            confirmation_count=confirmation_count,
        )

    # Fuera de la transacción: un consumidor lento o que falle no debe poder
    # revertir el cambio de estado (US-011).
    report_status_changed.send(
        sender=Report,
        report=locked,
        previous_status=previous_status,
        new_status=transition.target,
        changed_by=changed_by,
        reason=reason,
        # Explícito y no deducido del `history`: quien escucha el evento tiene
        # que poder distinguir dos transiciones que llegan al mismo estado sin
        # depender de la forma del par de estados (US-040).
        origin=transition.origin,
        history=history,
    )

    if assignment is not None:
        report_area_assigned.send(
            sender=Report,
            report=locked,
            assignment=assignment,
            assigned_by=changed_by,
        )

    report.refresh_from_db()
    return locked


def _assign_area(report: Report, area, *, assigned_by) -> ReportAreaAssignment:
    """Vincula el área al reporte y deja el asiento de la asignación.

    No guarda el reporte: lo hace quien la llama, en el mismo ``save()`` que el
    resto de los campos, para que no queden dos escrituras donde el dominio
    tiene un solo hecho.
    """
    previous_area = report.operational_area
    report.operational_area = area
    report.area_assigned_at = timezone.now()
    return ReportAreaAssignment.objects.create(
        report=report,
        previous_area=previous_area,
        area=area,
        assigned_by=assigned_by,
    )


def reassign_area(report: Report, area, *, assigned_by) -> ReportAreaAssignment:
    """Cambia el área de un reporte **sin** moverlo de estado (US-028).

    Es la contracara de ``procesar``: aquella asigna el área entrando a *En
    proceso*, esta la cambia una vez adentro. Por eso no es una transición y no
    pasa por la máquina de estados —el reporte no cambia de estado— pero sí
    respeta la misma regla: un reporte En proceso nunca queda sin área.

    Solo vale en *En proceso*. Antes de eso todavía no hay nada que distribuir,
    y en un estado final o archivado el área que intervino es historia y no se
    toca.
    """
    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.status != AREA_REASSIGNMENT_STATUS:
            raise _unavailable(locked, "reasignar", Actor.MUNICIPAL_AGENT)
        if locked.operational_area_id == area.pk:
            raise TransitionError(
                SAME_AREA_MESSAGE,
                current_status=locked.status,
                available=("reasignar",),
            )

        assignment = _assign_area(locked, area, assigned_by=assigned_by)
        locked.save(
            update_fields=["operational_area", "area_assigned_at", "updated_at"],
        )

    report_area_assigned.send(
        sender=Report,
        report=locked,
        assignment=assignment,
        assigned_by=assigned_by,
    )
    report.refresh_from_db()
    return assignment
