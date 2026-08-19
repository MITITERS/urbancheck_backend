"""Completa la dirección de los reportes que solo tienen coordenadas.

Los reportes creados desde el GPS antes de que existiera la geocodificación
inversa quedaron con ``address`` vacío, así que la búsqueda por calle, barrio o
localidad (US-020) no los encuentra. Este comando los rellena una sola vez.
"""

import time

from django.core.management.base import BaseCommand

from urbancheck.reports.geocoding import reverse_geocode
from urbancheck.reports.models import Report

# Nominatim admite como máximo 1 consulta por segundo en su servidor público.
_THROTTLE_SECONDS = 1.1


class Command(BaseCommand):
    help = "Completa la dirección de los reportes que tienen coordenadas pero no dirección."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra qué se resolvería, sin guardar nada.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        pending = Report.objects.filter(
            address="",
            latitude__isnull=False,
            longitude__isnull=False,
        ).order_by("id")

        total = pending.count()
        if not total:
            self.stdout.write("No hay reportes con coordenadas y sin dirección.")
            return

        self.stdout.write(f"Reportes a procesar: {total}")
        resolved = 0

        for index, report in enumerate(pending):
            address = reverse_geocode(report.latitude, report.longitude)
            if address:
                resolved += 1
                self.stdout.write(f"  #{report.id}  {address}")
                if not dry_run:
                    report.address = address
                    report.save(update_fields=["address"])
            else:
                self.stdout.write(
                    self.style.WARNING(f"  #{report.id}  sin resultado"),
                )

            # No dormimos después del último para no alargar el comando de gusto.
            if index < total - 1:
                time.sleep(_THROTTLE_SECONDS)

        suffix = " (dry-run, no se guardó nada)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(f"Resueltos {resolved} de {total}{suffix}."),
        )
