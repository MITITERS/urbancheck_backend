"""Ciudad/provincia y área de cobertura de la municipalidad.

Los dos campos de texto se **renombran**, no se borran y recrean: los municipios
ya cargados conservan sus datos. El centro y el radio se agregan nulos porque no
hay forma de inventarlos para las filas existentes; un municipio sin ellos no
recibe reportes nuevos hasta que un administrador los complete.
"""

from django.db import migrations
from django.db import models

# Centros conocidos de los municipios que carga el seed de desarrollo, para que
# el entorno local quede utilizable después de migrar.
KNOWN_CENTERS = {
    ("Villa María", "Córdoba"): (-32.4103, -63.2400, 15),
    ("Villa Nueva", "Córdoba"): (-32.4333, -63.2333, 10),
}


def fill_known_centers(apps, schema_editor):
    municipality_model = apps.get_model("municipalities", "Municipality")
    for municipality in municipality_model.objects.all():
        center = KNOWN_CENTERS.get((municipality.city, municipality.province))
        if center is None:
            continue
        municipality.latitude, municipality.longitude, municipality.coverage_radius_km = (
            center
        )
        municipality.save(
            update_fields=["latitude", "longitude", "coverage_radius_km"],
        )


def noop(apps, schema_editor):
    """Los campos se borran al revertir: no hay nada que deshacer."""


class Migration(migrations.Migration):
    dependencies = [
        ("municipalities", "0001_initial"),
    ]

    operations = [
        # La constraint se quita primero: nombra las columnas que se renombran.
        migrations.RemoveConstraint(
            model_name="municipality",
            name="unique_municipality_name_locality",
        ),
        migrations.RenameField(
            model_name="municipality",
            old_name="name",
            new_name="city",
        ),
        migrations.RenameField(
            model_name="municipality",
            old_name="locality",
            new_name="province",
        ),
        migrations.AlterField(
            model_name="municipality",
            name="city",
            field=models.CharField(max_length=120, verbose_name="city"),
        ),
        migrations.AlterField(
            model_name="municipality",
            name="province",
            field=models.CharField(max_length=120, verbose_name="province"),
        ),
        migrations.AddField(
            model_name="municipality",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name="latitude",
            ),
        ),
        migrations.AddField(
            model_name="municipality",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name="longitude",
            ),
        ),
        migrations.AddField(
            model_name="municipality",
            name="coverage_radius_km",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Distancia desde el centro dentro de la cual llegan los reportes."
                ),
                max_digits=6,
                null=True,
                verbose_name="coverage radius (km)",
            ),
        ),
        migrations.AddField(
            model_name="municipality",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="active"),
        ),
        migrations.AlterModelOptions(
            name="municipality",
            options={
                "ordering": ["city", "province"],
                "verbose_name": "municipality",
                "verbose_name_plural": "municipalities",
            },
        ),
        migrations.AddConstraint(
            model_name="municipality",
            constraint=models.UniqueConstraint(
                fields=("city", "province"),
                name="unique_municipality_city_province",
            ),
        ),
        migrations.RunPython(fill_known_centers, noop),
    ]
