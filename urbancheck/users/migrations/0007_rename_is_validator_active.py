"""La baja lógica deja de ser del validador y pasa a ser de la cuenta de trabajo.

Es un ``RenameField`` y no un borrar-y-crear a propósito: las bajas ya
registradas tienen que sobrevivir a la migración.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_user_is_validator_active"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="is_validator_active",
            new_name="is_work_account_active",
        ),
        migrations.AlterField(
            model_name="user",
            name="is_work_account_active",
            field=models.BooleanField(
                default=True,
                help_text="Solo aplica a validadores y agentes municipales.",
                verbose_name="work account active",
            ),
        ),
    ]
