"""US-034 — cada reporte pertenece a una municipalidad.

Se hace en tres pasos dentro de una sola migración: se agrega el campo
nullable, se rellenan los reportes existentes con la municipalidad activa y
recién entonces se lo vuelve obligatorio. Así la migración corre sobre una base
con datos sin pedir un default artificial.
"""

import django.db.models.deletion
from django.db import migrations
from django.db import models

# Municipalidad con la que opera esta iteración del sistema.
DEFAULT_MUNICIPALITY = {"name": "Villa María", "locality": "Córdoba"}


def assign_active_municipality(apps, schema_editor):
    report_model = apps.get_model("reports", "Report")
    if not report_model.objects.exists():
        return

    municipality_model = apps.get_model("municipalities", "Municipality")
    municipality = municipality_model.objects.order_by("pk").first()
    if municipality is None:
        municipality = municipality_model.objects.create(**DEFAULT_MUNICIPALITY)
    report_model.objects.filter(municipality__isnull=True).update(
        municipality=municipality,
    )


def noop(apps, schema_editor):
    """El campo se borra al revertir: no hay nada que deshacer."""


class Migration(migrations.Migration):
    dependencies = [
        ("municipalities", "0001_initial"),
        ("reports", "0003_report_edited_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="municipality",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reports",
                to="municipalities.municipality",
            ),
        ),
        migrations.RunPython(assign_active_municipality, noop),
        migrations.AlterField(
            model_name="report",
            name="municipality",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reports",
                to="municipalities.municipality",
            ),
        ),
    ]
