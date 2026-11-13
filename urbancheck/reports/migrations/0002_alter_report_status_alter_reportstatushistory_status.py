# Generated manually on 2026-07-07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='report',
            name='status',
            field=models.CharField(choices=[('pendiente_validacion', 'Pendiente de validación'), ('reportado', 'Reportado'), ('en_proceso', 'En proceso'), ('resuelto', 'Resuelto'), ('cancelado', 'Cancelado'), ('archivado', 'Archivado')], default='pendiente_validacion', max_length=30),
        ),
        migrations.AlterField(
            model_name='reportstatushistory',
            name='status',
            field=models.CharField(choices=[('pendiente_validacion', 'Pendiente de validación'), ('reportado', 'Reportado'), ('en_proceso', 'En proceso'), ('resuelto', 'Resuelto'), ('cancelado', 'Cancelado'), ('archivado', 'Archivado')], max_length=30),
        ),
    ]
