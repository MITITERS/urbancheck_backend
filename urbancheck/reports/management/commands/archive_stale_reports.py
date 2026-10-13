"""Verificación periódica del archivado por inactividad (US-031).

Se corre a diario. La política vive en ``reports.archival``; esto solo la
dispara e informa el resultado, para que un cron y una tarea de Celery no sean
dos implementaciones distintas de la misma regla.
"""

from django.core.management.base import BaseCommand

from urbancheck.reports.archival import inactivity_days
from urbancheck.reports.archival import run_archival


class Command(BaseCommand):
    # El plazo **no** se interpola acá: `help` se evalúa al importar la clase, y
    # eso volvería a capturar el valor de configuración una sola vez. Se informa
    # al correr, que es cuando se sabe cuál está vigente.
    help = (
        "Archiva los reportes pendientes de validación sin interacción por el "
        "plazo configurado y avisa a los que están por cumplirlo."
    )

    def handle(self, *args, **options):
        result = run_archival()
        self.stdout.write(
            self.style.SUCCESS(
                f"Plazo vigente: {inactivity_days()} días. "
                f"Avisados: {result['warned']}. Archivados: {result['archived']}.",
            ),
        )
