from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0002_alter_report_status_alter_reportstatushistory_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
