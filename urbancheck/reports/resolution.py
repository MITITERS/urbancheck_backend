"""Cierre en terreno, confirmación y apelación (US-046, US-047 y US-048).

Los tres pasos de un mismo circuito, en un solo módulo porque comparten las
reglas: el operario cierra, corre una ventana de objeción, y el autor la deja
pasar o la usa. Separarlos habría repartido esas reglas en tres archivos que
después divergen.

Ninguna de las tres funciones escribe el estado del reporte: todas invocan la
máquina de estados única de US-013.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from urbancheck.reports.geo import haversine_meters

from .models import Report
from .models import ResolutionAppeal
from .models import ResolutionEvidence
from .services import TransitionError
from .services import apply_transition
from .state_machine import Actor
from .state_machine import closing_operation

CONFIRM_OPERATION = "confirmar_resolucion"
APPEAL_OPERATION = "apelar"


class TooFarError(Exception):
    """El operario no está en el lugar del problema (US-046, escenario 5).

    Lleva la distancia real para que la app pueda decir "estás a 320 m" en lugar
    de un mensaje genérico, igual que en la validación en terreno de US-036.
    """

    def __init__(self, distance: float, radius: int):
        super().__init__("Fuera del radio permitido.")
        self.distance = distance
        self.radius = radius


def objection_period() -> timedelta:
    """Cuánto dura la ventana de objeción del autor (US-047).

    Se lee de configuración en cada evaluación y **en minutos**: el default son
    siete días, pero la review necesita poder bajarlo a un par de minutos para
    demostrar la confirmación automática sin esperar una semana ni tocar código.
    """
    return timedelta(minutes=settings.RESOLUTION_OBJECTION_MINUTES)


def objection_warning_lead() -> timedelta:
    """Cuánto antes del vencimiento se le avisa al autor. Default: 24 horas."""
    return timedelta(minutes=settings.RESOLUTION_OBJECTION_WARNING_MINUTES)


def objection_deadline(report: Report):
    """Cuándo vence la ventana de objeción de este reporte, o ``None``.

    ``None`` mientras no haya un cierre del que contar: es lo que el detalle usa
    para decidir si muestra el plazo restante.
    """
    if report.closed_at is None:
        return None
    return report.closed_at + objection_period()


def check_proximity(report: Report, latitude: float, longitude: float) -> None:
    """Rechaza el cierre si el operario no está en el lugar.

    Usa la misma función de distancia y el mismo radio que la validación en
    terreno de US-036: dos implementaciones paralelas terminarían con dos
    criterios de "estar en el lugar".

    Un reporte sin coordenadas no se puede comprobar contra nada, así que pasa:
    es preferible eso a dejar sin poder cerrar un trabajo que sí se hizo.
    """
    if report.latitude is None or report.longitude is None:
        return
    distance = haversine_meters(latitude, longitude, report.latitude, report.longitude)
    radius = settings.VALIDATION_RADIUS_METERS
    if distance > radius:
        raise TooFarError(distance, radius)


def register_resolution(  # noqa: PLR0913 (cada parámetro es un dato del parte)
    report: Report,
    *,
    operator,
    photo,
    description: str,
    latitude: float,
    longitude: float,
) -> ResolutionEvidence:
    """El operario cierra el trabajo y deja su parte (US-046).

    La evidencia y la transición se escriben en la **misma transacción**: un
    reporte cerrado sin parte de trabajo, o un parte sobre un reporte que se
    quedó En proceso, no llegan a existir.

    A qué estado va lo decide ``closing_operation``: el primer cierre abre la
    ventana de objeción, el segundo —después de una apelación— es definitivo.
    """
    check_proximity(report, latitude, longitude)

    with transaction.atomic():
        evidence = ResolutionEvidence.objects.create(
            report=report,
            photo=photo,
            description=description,
            operator=operator,
            # El área **al momento del cierre**: un traslado posterior del
            # operario no puede reescribir quién se hizo cargo de este trabajo.
            operational_area=report.operational_area,
            latitude=latitude,
            longitude=longitude,
        )
        apply_transition(
            report,
            closing_operation(report),
            actor=Actor.OPERATOR,
            changed_by=operator,
        )
    return evidence


def appeal_resolution(
    report: Report,
    *,
    author,
    reason: str,
    photo,
) -> ResolutionAppeal:
    """El autor objeta un cierre que no resolvió el problema (US-048).

    Vuelve a *En proceso* **conservando el área operativa**: el trabajo mal
    ejecutado le corresponde a quien lo ejecutó, así que el reporte no vuelve a
    *Reportado* ni queda sin responsable.

    El tope de una apelación por reporte no se verifica acá: lo hace la guarda de
    la transición, sobre la fila ya bloqueada. Si estuviera acá, un segundo
    endpoint que llamara a la misma transición se lo saltearía.
    """
    with transaction.atomic():
        appeal = ResolutionAppeal.objects.create(
            report=report,
            # La evidencia objetada es la última registrada. Se guarda el
            # vínculo y no se la borra: el segundo cierre crea una nueva y las
            # dos quedan para poder compararlas.
            evidence=report.resolution_evidences.order_by("created_at").last(),
            author=author,
            reason=reason,
            photo=photo,
        )
        apply_transition(
            report,
            APPEAL_OPERATION,
            actor=Actor.CITIZEN,
            changed_by=author,
            reason=reason,
        )
    return appeal


def reports_due_for_confirmation(now=None):
    """Cierres cuya ventana de objeción venció sin apelación (US-047)."""
    now = now or timezone.now()
    return Report.objects.filter(
        status=Report.Status.RESUELTO_PENDIENTE,
        closed_at__lte=now - objection_period(),
    )


def reports_due_for_objection_warning(now=None):
    """Cierres a los que les queda menos que la antelación del aviso.

    Se excluyen los ya avisados: la verificación corre a diario y sin esa
    condición el vecino recibiría el mismo recordatorio varias veces.
    """
    now = now or timezone.now()
    period = objection_period()
    lead = objection_warning_lead()
    return Report.objects.filter(
        status=Report.Status.RESUELTO_PENDIENTE,
        closed_at__lte=now - (period - lead),
        closed_at__gt=now - period,
        objection_warning_sent_at__isnull=True,
    )


def run_confirmation(now=None) -> dict[str, int]:
    """Ejecuta la verificación periódica de la ventana de objeción.

    A diferencia del umbral de US-040, acá no hay evento que dispare la
    evaluación: el hecho relevante es el paso del tiempo.

    Primero los avisos y después las confirmaciones, para que un reporte que
    cruza las dos ventanas en la misma corrida —porque la tarea no corrió por
    unos días— se confirme en lugar de recibir un aviso que ya no sirve.

    Es idempotente: una segunda corrida sobre el mismo reporte no genera una
    transición duplicada, porque el reporte ya no está en el estado de partida.
    """
    # Import local: ``notifications`` importa ``reports`` a través del modelo.
    from urbancheck.notifications.services import (  # noqa: PLC0415
        notify_objection_deadline,
    )

    now = now or timezone.now()

    warned = 0
    for report in reports_due_for_objection_warning(now).select_related("author"):
        notify_objection_deadline(report, deadline=objection_deadline(report))
        report.objection_warning_sent_at = now
        report.save(update_fields=["objection_warning_sent_at"])
        warned += 1

    confirmed = 0
    for report in reports_due_for_confirmation(now):
        try:
            apply_transition(
                report,
                CONFIRM_OPERATION,
                actor=Actor.SYSTEM,
                # El silencio del autor no tiene responsable individual.
                changed_by=None,
            )
        except TransitionError:
            # Alguien lo movió entre la consulta y la transición —una apelación
            # justo a tiempo, o la confirmación anticipada del agente—. No es un
            # error: el reporte dejó de ser candidato, que es lo que se quería.
            continue
        confirmed += 1

    return {"warned": warned, "confirmed": confirmed}
