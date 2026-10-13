"""Reintenta las comparaciones de cierres que no terminaron (US-015).

Sirve después de cargar la clave del servicio de visión, o de una caída larga
del proveedor: los cierres registrados mientras tanto quedaron como "comparación
no disponible" y no se vuelven a intentar solos.

Corre en el momento y no por Celery, para poder informar el resultado. Por eso
no usa ``compare_resolution.apply``: con ``CELERY_TASK_EAGER_PROPAGATES`` —que
el entorno local activa— el reintento de la tarea sale como excepción en lugar
de ejecutarse, y la comparación quedaba colgada en pendiente.
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from urbancheck.reports import vision
from urbancheck.reports.comparison import mark_unavailable
from urbancheck.reports.comparison import reset_for_retry
from urbancheck.reports.comparison import run_comparison
from urbancheck.reports.models import ResolutionComparison
from urbancheck.reports.vision import TransientVisionError
from urbancheck.reports.vision import VisionError

#: Espera entre intentos. Más corta que la de la tarea: acá hay alguien mirando.
RETRY_WAIT_SECONDS = 5


class Command(BaseCommand):
    help = (
        "Vuelve a ejecutar las comparaciones automáticas de cierres que quedaron "
        "no disponibles o colgadas en pendiente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            type=int,
            help="Solo los cierres de este reporte (su id, no su número).",
        )

    def handle(self, *args, **options):
        if not vision.is_configured():
            msg = (
                "Falta DJANGO_RESOLUTION_COMPARISON_API_KEY: sin clave la "
                "comparación no se puede ejecutar."
            )
            raise CommandError(msg)

        evidence_ids = reset_for_retry(options["report"])
        if not evidence_ids:
            self.stdout.write("No hay comparaciones para reintentar.")
            return

        for evidence_id in evidence_ids:
            self._compare(evidence_id)
            comparison = ResolutionComparison.objects.select_related(
                "evidence",
            ).get(evidence_id=evidence_id)
            if comparison.verdict:
                outcome = f"{comparison.verdict}: {comparison.explanation}"
            else:
                outcome = f"{comparison.status} ({comparison.failure_reason})"
            self.stdout.write(
                f"Reporte {comparison.evidence.report_id}, "
                f"cierre {evidence_id} → {outcome}",
            )

    def _compare(self, evidence_id: int) -> None:
        """Mismas reglas que la tarea: solo se reintentan los fallos pasajeros."""
        attempts = settings.RESOLUTION_COMPARISON_MAX_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                run_comparison(evidence_id)
            except TransientVisionError as exc:
                if attempt == attempts:
                    mark_unavailable(evidence_id, exc.code)
                    return
                self.stdout.write(f"  {exc.code}; reintento {attempt}…")
                time.sleep(RETRY_WAIT_SECONDS)
            except VisionError as exc:
                mark_unavailable(evidence_id, exc.code)
                return
            else:
                return
