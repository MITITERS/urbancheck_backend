"""Ejecución de transiciones de estado del reporte (US-013).

La validación vive acá y no en un serializer: una transición inválida tiene que
ser imposible incluso llamando al modelo directamente desde el shell.
"""

from __future__ import annotations

from django.db import transaction

from .models import Report
from .models import ReportStatusHistory
from .signals import report_status_changed
from .state_machine import Actor
from .state_machine import Transition
from .state_machine import get_transition
from .state_machine import transitions_from

REASON_REQUIRED_MESSAGE = "Esta acción requiere indicar un motivo."


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


def _unavailable(report: Report, operation: str, actor: Actor) -> TransitionError:
    available = tuple(t.operation for t in transitions_from(report.status, actor))
    return TransitionError(
        f"No se puede ejecutar «{operation}» sobre un reporte en estado "
        f"«{report.get_status_display()}».",
        current_status=report.status,
        available=available,
    )


def apply_transition(
    report: Report,
    operation: str,
    *,
    actor: Actor,
    changed_by,
    reason: str = "",
) -> Report:
    """Mueve el reporte de estado y deja el asiento del historial.

    Bloquea la fila con ``select_for_update`` dentro de una transacción, para que
    dos pestañas del panel no puedan ejecutar dos transiciones simultáneas sobre
    el mismo reporte: la segunda encuentra el estado ya cambiado y se rechaza.
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

    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.status != transition.source:
            raise _unavailable(locked, operation, actor)

        previous_status = locked.status
        locked.status = transition.target
        locked.save(update_fields=["status", "updated_at"])

        history = ReportStatusHistory.objects.create(
            report=locked,
            status=transition.target,
            previous_status=previous_status,
            changed_by=changed_by,
            reason=reason,
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
        history=history,
    )

    report.refresh_from_db()
    return locked
