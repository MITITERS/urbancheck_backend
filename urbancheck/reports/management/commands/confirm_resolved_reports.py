"""Verificación de la ventana de objeción del cierre (US-047).

La política vive en ``reports.resolution``; esto solo la dispara e informa el
resultado, para que un cron y una tarea de Celery no sean dos implementaciones
distintas de la misma regla.
"""

from django.core.management.base import BaseCommand

from urbancheck.reports.resolution import objection_period
from urbancheck.reports.resolution import run_confirmation


class Command(BaseCommand):
    help = (
        "Confirma como Resueltos los reportes cerrados por un operario cuya "
        "ventana de objeción venció sin apelación, y avisa a los autores cuyo "
        "plazo está por vencer."
    )

    def handle(self, *args, **options):
        result = run_confirmation()
        self.stdout.write(
            self.style.SUCCESS(
                f"Plazo de objeción: {objection_period()}. "
                f"Avisados: {result['warned']}. Confirmados: {result['confirmed']}.",
            ),
        )
