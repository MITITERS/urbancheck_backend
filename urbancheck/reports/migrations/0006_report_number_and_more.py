"""Número de reporte por municipalidad.

El backfill numera lo que ya existe por orden de creación dentro de cada
municipio, que es el mismo criterio con el que se numeran los nuevos: así el
histórico y lo que viene son una sola secuencia y no dos.
"""

from django.conf import settings
from django.db import migrations, models


def assign_numbers(apps, schema_editor):
    """Numera los reportes existentes, uno por municipio, por antigüedad."""
    Report = apps.get_model("reports", "Report")
    municipality_ids = (
        Report.objects.order_by("municipality_id")
        .values_list("municipality_id", flat=True)
        .distinct()
    )
    for municipality_id in municipality_ids:
        reports = Report.objects.filter(municipality_id=municipality_id).order_by(
            "created_at",
            "id",
        )
        # ``id`` desempata: dos reportes pueden compartir ``created_at`` y el
        # orden tiene que ser total, o el backfill no sería reproducible.
        for number, report in enumerate(reports, start=1):
            report.number = number
        Report.objects.bulk_update(reports, ["number"])


def clear_numbers(apps, schema_editor):
    apps.get_model("reports", "Report").objects.update(number=None)


class Migration(migrations.Migration):
    dependencies = [
        ("municipalities", "0002_coverage_area"),
        ("reports", "0005_status_history_detail"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="number",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        # El backfill va antes de la restricción: con los datos ya numerados, si
        # el backfill tuviera un error la migración falla acá y no deja la base a
        # medio migrar.
        migrations.RunPython(assign_numbers, clear_numbers),
        migrations.AddConstraint(
            model_name="report",
            constraint=models.UniqueConstraint(
                fields=("municipality", "number"),
                name="unique_report_number_per_municipality",
            ),
        ),
    ]
