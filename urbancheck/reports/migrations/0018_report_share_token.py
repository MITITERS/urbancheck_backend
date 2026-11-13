# Enlace para compartir un reporte (US-030).
#
# En tres pasos, porque un ``default=uuid.uuid4`` en ``AddField`` se evalúa una
# sola vez y les daría a todas las filas existentes **el mismo** token, y la
# restricción de único fallaría: primero el campo nulo, después un token por
# fila, y recién ahí la restricción.

import uuid

from django.db import migrations
from django.db import models


def give_every_report_a_token(apps, schema_editor):
    Report = apps.get_model("reports", "Report")
    for report in Report.objects.filter(share_token__isnull=True).only("pk"):
        Report.objects.filter(pk=report.pk).update(share_token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0017_history_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="share_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(give_every_report_a_token, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="report",
            name="share_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
