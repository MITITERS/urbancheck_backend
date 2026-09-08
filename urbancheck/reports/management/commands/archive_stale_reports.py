"""Verificación periódica del archivado por inactividad (US-031).

Se corre a diario. La política vive en ``reports.archival``; esto solo la
dispara e informa el resultado, para que un cron y una tarea de Celery no sean
dos implementaciones distintas de la misma regla.
"""

from django.core.management.base import BaseCommand

from urbancheck.reports.archival import INACTIVITY_DAYS
from urbancheck.reports.archival import run_archival


class Command(BaseCommand):
    help = (
        "Archiva los reportes pendientes de validación sin interacción por "
        f"{INACTIVITY_DAYS} días y avisa a los que están por cumplir el plazo."
    )

    def handle(self, *args, **options):
        result = run_archival()
        self.stdout.write(
            self.style.SUCCESS(
                f"Avisados: {result['warned']}. Archivados: {result['archived']}.",
            ),
        )
