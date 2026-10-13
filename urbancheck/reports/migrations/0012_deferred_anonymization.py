"""Publicación diferida hasta completar el difuminado (US-042).

Suma a los tres modelos con foto el estado de procesamiento y el campo donde
espera la original, y cierra con un ``CheckConstraint`` que impide guardar una
foto publicada sin haber pasado por el difuminado.

**Las filas existentes se marcan como ``procesada`` sin re-procesarlas.** Es una
desviación consciente del escenario 9 de la historia, decidida por el equipo: no
se ejecuta el procesamiento retroactivo ni se purga el entorno. Consecuencia a
tener presente: una imagen cargada antes de US-041 sigue publicada sin difuminar,
y esta migración no lo arregla. Cerrarlo más adelante es un comando chico
—recorrer las fotos guardadas, correrles ``anonymize()`` sobre el archivo actual
y volver a marcarlas—, idempotente porque difuminar algo ya difuminado no
cambia nada.

El orden de las operaciones importa: el ``RunPython`` va **antes** de los
``AddConstraint``, o el constraint se evalúa sobre las filas viejas —que tienen
foto y ``photo_status='pendiente'``— y la migración falla.
"""


import urbancheck.anonymization.storage
from django.conf import settings
from django.db import migrations, models


#: Los modelos que llevan el estado de procesamiento, en un solo lugar.
PHOTO_MODELS = ("Report", "ResolutionEvidence", "ResolutionAppeal")


def mark_existing_photos_as_processed(apps, schema_editor):
    """Todo lo que ya existía queda publicado tal como está.

    Ver la nota del módulo: es la decisión sobre el escenario 9. Marcarlas como
    ``pendiente`` las escondería sin que haya un original con el que
    procesarlas, y dejaría el entorno sin datos visibles.
    """
    for name in PHOTO_MODELS:
        apps.get_model("reports", name).objects.update(photo_status="procesada")


class Migration(migrations.Migration):

    dependencies = [
        ('municipalities', '0004_operationalarea'),
        ('reports', '0011_report_complaint'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='photo_attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='intentos de procesamiento'),
        ),
        migrations.AddField(
            model_name='report',
            name='photo_failed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='fallo definitivo'),
        ),
        migrations.AddField(
            model_name='report',
            name='photo_pending',
            field=models.FileField(blank=True, storage=urbancheck.anonymization.storage.pending_photo_storage, upload_to=urbancheck.anonymization.storage.pending_upload_to, verbose_name='foto sin procesar'),
        ),
        migrations.AddField(
            model_name='report',
            name='photo_queued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='encolada'),
        ),
        migrations.AddField(
            model_name='report',
            name='photo_status',
            field=models.CharField(choices=[('pendiente', 'En procesamiento'), ('procesada', 'Procesada'), ('fallida', 'No se pudo procesar')], default='pendiente', max_length=10, verbose_name='estado del procesamiento'),
        ),
        migrations.AddField(
            model_name='resolutionappeal',
            name='photo_attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='intentos de procesamiento'),
        ),
        migrations.AddField(
            model_name='resolutionappeal',
            name='photo_failed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='fallo definitivo'),
        ),
        migrations.AddField(
            model_name='resolutionappeal',
            name='photo_pending',
            field=models.FileField(blank=True, storage=urbancheck.anonymization.storage.pending_photo_storage, upload_to=urbancheck.anonymization.storage.pending_upload_to, verbose_name='foto sin procesar'),
        ),
        migrations.AddField(
            model_name='resolutionappeal',
            name='photo_queued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='encolada'),
        ),
        migrations.AddField(
            model_name='resolutionappeal',
            name='photo_status',
            field=models.CharField(choices=[('pendiente', 'En procesamiento'), ('procesada', 'Procesada'), ('fallida', 'No se pudo procesar')], default='pendiente', max_length=10, verbose_name='estado del procesamiento'),
        ),
        migrations.AddField(
            model_name='resolutionevidence',
            name='photo_attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='intentos de procesamiento'),
        ),
        migrations.AddField(
            model_name='resolutionevidence',
            name='photo_failed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='fallo definitivo'),
        ),
        migrations.AddField(
            model_name='resolutionevidence',
            name='photo_pending',
            field=models.FileField(blank=True, storage=urbancheck.anonymization.storage.pending_photo_storage, upload_to=urbancheck.anonymization.storage.pending_upload_to, verbose_name='foto sin procesar'),
        ),
        migrations.AddField(
            model_name='resolutionevidence',
            name='photo_queued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='encolada'),
        ),
        migrations.AddField(
            model_name='resolutionevidence',
            name='photo_status',
            field=models.CharField(choices=[('pendiente', 'En procesamiento'), ('procesada', 'Procesada'), ('fallida', 'No se pudo procesar')], default='pendiente', max_length=10, verbose_name='estado del procesamiento'),
        ),
        migrations.AlterField(
            model_name='resolutionappeal',
            name='photo',
            field=models.ImageField(blank=True, upload_to='appeals/%Y/%m/'),
        ),
        migrations.RunPython(
            mark_existing_photos_as_processed,
            migrations.RunPython.noop,
            elidable=False,
        ),
        migrations.AddConstraint(
            model_name='report',
            constraint=models.CheckConstraint(condition=models.Q(('photo', ''), ('photo_status', 'procesada'), _connector='OR'), name='report_photo_only_when_processed'),
        ),
        migrations.AddConstraint(
            model_name='resolutionappeal',
            constraint=models.CheckConstraint(condition=models.Q(('photo', ''), ('photo_status', 'procesada'), _connector='OR'), name='appeal_photo_only_when_processed'),
        ),
        migrations.AddConstraint(
            model_name='resolutionevidence',
            constraint=models.CheckConstraint(condition=models.Q(('photo', ''), ('photo_status', 'procesada'), _connector='OR'), name='evidence_photo_only_when_processed'),
        ),
    ]
