"""Comparación automática del antes y el después de un cierre (US-015).

El circuito es:

1. ``register_comparison`` corre dentro de la transacción del cierre y deja la
   fila en pendiente. El operario no espera a un servicio externo en la calle.
2. ``enqueue_comparison`` corre cuando el difuminado de la foto del cierre
   termina (US-042): recién ahí hay una imagen publicable que comparar, y es la
   difuminada, que es la única que se puede mandar a un servicio externo.
3. La tarea ``compare_resolution`` llama a ``run_comparison``, que es la que
   habla con el cliente de visión y guarda el veredicto.

**Nada de este módulo toca el reporte.** El veredicto es un indicio para que el
agente priorice qué revisar: no cambia el estado, no toca el plazo de US-047 y
no habilita ni impide transiciones. Un fallo acá tampoco puede bloquear un
cierre: el peor caso es "comparación no disponible".
"""

from __future__ import annotations

import logging
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import BooleanField
from django.db.models import Case
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.db.models import Value
from django.db.models import When
from django.utils import timezone

from . import vision
from .models import Report
from .models import ResolutionComparison
from .models import ResolutionEvidence

if TYPE_CHECKING:
    from django.db.models.fields.files import FieldFile

logger = logging.getLogger(__name__)

Status = ResolutionComparison.Status


def register_comparison(evidence: ResolutionEvidence) -> ResolutionComparison:
    """Registra la comparación de un cierre recién creado, **sin encolarla**.

    Se llama dentro de la transacción del cierre: si el cierre se revierte, la
    fila se revierte con él.

    Encolar acá dejó de tener sentido con US-042. La foto del cierre entra a la
    cola de difuminado y ``evidence.photo`` está vacía en este instante, así que
    ``_has_material`` daría falso y **toda** comparación terminaría en
    ``NO_MATERIAL``, en silencio y sin que nada lo señale. Y aunque se esperara,
    lo que hay que comparar es la versión difuminada, no la original. El disparo
    quedó del otro lado: lo hace ``enqueue_comparison`` cuando el difuminado
    termina (ver los hooks en ``reports.apps``).

    La fila se crea igual y ahora, no cuando la foto esté lista: el panel tiene
    que poder mostrar "comparación pendiente" desde el momento del cierre.
    """
    if not vision.is_configured():
        status, reason = Status.UNAVAILABLE, "not_configured"
    else:
        status, reason = Status.PENDING, ""

    return ResolutionComparison.objects.create(
        evidence=evidence,
        status=status,
        failure_reason=reason,
        completed_at=None if status == Status.PENDING else timezone.now(),
    )


def enqueue_comparison(evidence: ResolutionEvidence) -> None:
    """Dispara la comparación ahora que la foto del cierre está difuminada.

    Acá sí se mira el material: es el primer momento en que las dos fotos —la
    del reporte y la del cierre— existen o no de verdad. Sin material no hay
    nada que comparar y la fila se cierra como ``NO_MATERIAL``, que es lo que
    hacía US-015 antes de que el difuminado se volviera diferido.
    """
    comparison = ResolutionComparison.objects.filter(evidence=evidence).first()
    if comparison is None or comparison.status != Status.PENDING:
        return
    if not _has_material(evidence):
        comparison.status = Status.NO_MATERIAL
        comparison.failure_reason = ""
        comparison.completed_at = timezone.now()
        comparison.save(update_fields=["status", "failure_reason", "completed_at"])
        return
    transaction.on_commit(partial(_enqueue, evidence.pk))


def _enqueue(evidence_id: int) -> None:
    """Encola la tarea sin dejar que un broker caído rompa el cierre.

    Corre después del commit: el cierre ya existe y el operario ya tiene su
    respuesta en camino. Si Redis no contesta, la comparación queda no
    disponible y el resto sigue igual (escenario 5).
    """
    # Import local: ``tasks`` importa este módulo.
    from .tasks import compare_resolution  # noqa: PLC0415

    try:
        compare_resolution.delay(evidence_id)
    except Exception:  # noqa: BLE001 (cualquier falla del broker vale lo mismo)
        logger.warning(
            "No se pudo encolar la comparación de la evidencia %s.",
            evidence_id,
            exc_info=True,
        )
        mark_unavailable(evidence_id, "enqueue_failed")


def run_comparison(evidence_id: int) -> ResolutionComparison | None:
    """Ejecuta la comparación de una evidencia y persiste el resultado.

    Siempre compara contra la foto **original del reporte**, nunca contra la de
    un cierre anterior: en un segundo cierre tras una apelación, la pregunta
    sigue siendo si se resolvió lo que el vecino reportó (escenario 7).

    Deja propagar los ``VisionError`` para que la tarea decida si reintenta.
    Es idempotente: una comparación que ya no está pendiente no se repite.
    """
    comparison = (
        ResolutionComparison.objects.select_related("evidence__report")
        .filter(evidence_id=evidence_id)
        .first()
    )
    if comparison is None or comparison.status != Status.PENDING:
        return comparison

    comparison.attempts += 1
    comparison.save(update_fields=["attempts"])

    evidence = comparison.evidence
    report = evidence.report
    # Se vuelve a mirar al ejecutar: una imagen puede haberse eliminado entre el
    # cierre y la tarea (US-043).
    original = _read(report.photo)
    resolution = _read(evidence.photo)
    if original is None or resolution is None:
        return _finish(comparison, status=Status.NO_MATERIAL)

    result = vision.compare_images(
        original,
        resolution,
        category=report.category,
        description=evidence.description,
    )
    comparison.verdict = result.verdict
    comparison.explanation = result.explanation
    comparison.model_name = result.model_name
    return _finish(comparison, status=Status.COMPLETED)


def mark_unavailable(evidence_id: int, reason: str) -> None:
    """Cierra una comparación pendiente sin veredicto.

    Solo actúa sobre pendientes: un reintento tardío no pisa un veredicto que
    ya se guardó.
    """
    ResolutionComparison.objects.filter(
        evidence_id=evidence_id,
        status=Status.PENDING,
    ).update(
        status=Status.UNAVAILABLE,
        failure_reason=reason[:50],
        completed_at=timezone.now(),
    )


#: Una comparación pendiente hace más de esto no está en curso: se cortó a la
#: mitad (un worker que murió, un reintento que no se ejecutó).
STALE_PENDING_AFTER = timedelta(minutes=15)


def reset_for_retry(report_id: int | None = None) -> list[int]:
    """Vuelve a dejar listas para correr las comparaciones que no terminaron.

    Son las no disponibles y las pendientes colgadas. Sirve para después de un
    fallo que ya se resolvió: la clave que faltaba, una caída larga del
    proveedor. Devuelve las evidencias a comparar; quién las ejecuta lo decide
    el llamador. Las que quedaron sin material no se tocan: faltaba una imagen,
    y reintentar no la trae de vuelta.
    """
    if report_id is None:
        pending = Q(
            status=Status.PENDING,
            requested_at__lt=timezone.now() - STALE_PENDING_AFTER,
        )
    else:
        # Pedida para un reporte puntual, la intención es explícita: cualquier
        # pendiente de ese reporte se vuelve a correr.
        pending = Q(status=Status.PENDING)
    comparisons = ResolutionComparison.objects.filter(
        Q(status=Status.UNAVAILABLE) | pending,
    )
    if report_id is not None:
        comparisons = comparisons.filter(evidence__report_id=report_id)
    evidence_ids = list(comparisons.values_list("evidence_id", flat=True))
    comparisons.update(
        status=Status.PENDING,
        failure_reason="",
        attempts=0,
        completed_at=None,
    )
    return evidence_ids


def closure_review_annotation() -> Case:
    """Expresión para anotar si un reporte es un cierre a revisar (escenario 3).

    Lo es mientras está en la ventana de objeción y la comparación de su
    **último** cierre terminó con un veredicto dudoso. El último, porque en un
    segundo cierre lo que importa es el trabajo nuevo, no el que ya se objetó.
    Confirmado el reporte, la señal se apaga: ya no hay nada que priorizar.
    """
    latest_evidence = (
        ResolutionEvidence.objects.filter(report_id=OuterRef(OuterRef("pk")))
        .order_by("-created_at", "-pk")
        .values("pk")[:1]
    )
    doubtful = (
        ResolutionComparison.objects.filter(
            evidence_id=Subquery(latest_evidence),
            status=Status.COMPLETED,
        )
        .exclude(verdict="")
        .exclude(verdict=ResolutionComparison.Verdict.CONSISTENT)
    )
    return Case(
        When(status=Report.Status.RESUELTO_PENDIENTE, then=Exists(doubtful)),
        default=Value(value=False),
        output_field=BooleanField(),
    )


def needs_closure_review(report: Report) -> bool:
    """Lo mismo que ``closure_review_annotation``, calculado en Python.

    Es el respaldo del serializer cuando el queryset no trae la anotación. Usa
    ``.all()`` para aprovechar el prefetch de evidencias si lo hay.
    """
    if report.status != Report.Status.RESUELTO_PENDIENTE:
        return False
    evidences = list(report.resolution_evidences.all())
    if not evidences:
        return False
    latest = max(evidences, key=lambda evidence: (evidence.created_at, evidence.pk))
    try:
        comparison = latest.comparison
    except ResolutionComparison.DoesNotExist:
        return False
    return comparison.status == Status.COMPLETED and comparison.is_doubtful


def _finish(comparison: ResolutionComparison, *, status: str) -> ResolutionComparison:
    comparison.status = status
    comparison.completed_at = timezone.now()
    comparison.save(
        update_fields=[
            "status",
            "verdict",
            "explanation",
            "model_name",
            "completed_at",
        ],
    )
    return comparison


def _has_material(evidence: ResolutionEvidence) -> bool:
    return _exists(evidence.report.photo) and _exists(evidence.photo)


def _exists(field: FieldFile) -> bool:
    if not field or not field.name:
        return False
    try:
        return field.storage.exists(field.name)
    except OSError:
        return False


def _read(field: FieldFile) -> bytes | None:
    """Los bytes de la imagen tal como está almacenada, o ``None`` si no está.

    Lo almacenado es siempre la versión difuminada de US-041: es lo único que
    puede salir hacia el servicio externo (escenario 10).
    """
    name = field.name
    if not name or not _exists(field):
        return None
    try:
        with field.storage.open(name, "rb") as handle:
            return handle.read()
    except OSError:
        return None
