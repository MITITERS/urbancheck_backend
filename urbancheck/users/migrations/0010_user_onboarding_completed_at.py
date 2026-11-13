# Tutorial de bienvenida (US-051).

from django.db import migrations
from django.db import models
from django.utils import timezone


def mark_existing_users(apps, schema_editor):
    """Las cuentas que ya existen al desplegar no reciben el tutorial.

    Ya usan la aplicación: mostrárselo de golpe es una interrupción sin valor
    (escenario 9). Se les pone la fecha del despliegue, así el escenario se
    cumple sin ninguna condición extra en el código: para la app, una cuenta
    preexistente es simplemente una que ya lo vio. Aplica a todos los roles; a
    las cuentas de trabajo no se les muestra de todos modos.
    """
    User = apps.get_model("users", "User")
    User.objects.filter(onboarding_completed_at__isnull=True).update(
        onboarding_completed_at=timezone.now(),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_avatar_without_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="onboarding_completed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Cuándo terminó u omitió el tutorial de bienvenida.",
                null=True,
                verbose_name="onboarding completed at",
            ),
        ),
        migrations.RunPython(mark_existing_users, migrations.RunPython.noop),
    ]
