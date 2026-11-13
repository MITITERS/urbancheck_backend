from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_avatar_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_public',
            field=models.BooleanField(default=True, help_text='Si se desactiva, otros usuarios no ven tus reportes ni tus estadísticas.', verbose_name='public profile'),
        ),
    ]
