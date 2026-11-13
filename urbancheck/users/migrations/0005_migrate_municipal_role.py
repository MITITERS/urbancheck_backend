from django.db import migrations

OLD_ROLE = "municipal"
NEW_ROLE = "agente_municipal"


def forwards(apps, schema_editor):
    """El rol ``municipal`` de la iteración anterior pasa a ``agente_municipal``.

    US-017 divide el rol municipal en administrador de plataforma y agente
    municipal; los usuarios existentes son todos agentes.
    """
    user_model = apps.get_model("users", "User")
    user_model.objects.filter(role=OLD_ROLE).update(role=NEW_ROLE)


def backwards(apps, schema_editor):
    user_model = apps.get_model("users", "User")
    user_model.objects.filter(role=NEW_ROLE).update(role=OLD_ROLE)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_user_municipality_user_must_change_password_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
