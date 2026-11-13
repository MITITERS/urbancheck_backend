"""El área de cobertura pasa de círculo a polígono.

Los municipios ya cargados tienen centro y radio. Borrar el radio sin más los
dejaría sin cobertura, y un municipio sin cobertura deja de recibir reportes:
la baja sería silenciosa y solo se notaría cuando un vecino no pudiera reportar.
Por eso el círculo se convierte en el polígono que lo aproxima antes de que el
campo desaparezca.

La conversión no mejora ningún límite —un círculo aproximado sigue siendo un
círculo— pero preserva exactamente el comportamiento anterior. Ajustar el
trazado a los límites reales es trabajo del administrador, municipio por
municipio, desde el panel.
"""

from __future__ import annotations

import math

from django.db import migrations
from django.db import models

#: Vértices con los que se aproxima un círculo. Con 32 el error contra el
#: círculo real es menor al 0,5% del radio: por debajo de lo que cualquiera
#: podría notar en un límite municipal.
CIRCLE_VERTICES = 32

#: Un grado de latitud son ~111,32 km en cualquier punto del planeta. En
#: longitud, esa distancia se achica con el coseno de la latitud.
KM_PER_DEGREE = 111.32


def circle_to_polygon(latitude, longitude, radius_km):
    """Polígono de ``CIRCLE_VERTICES`` lados que aproxima el círculo."""
    lat = float(latitude)
    lng = float(longitude)
    radius = float(radius_km)
    lat_delta = radius / KM_PER_DEGREE
    # Cerca de los polos el coseno tiende a cero y la corrección explota. No es
    # el caso de ningún municipio argentino, pero el piso evita una división
    # por algo demasiado chico si alguna vez se carga uno.
    lng_delta = radius / (KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))

    points = []
    for vertex in range(CIRCLE_VERTICES):
        angle = 2 * math.pi * vertex / CIRCLE_VERTICES
        points.append(
            [
                round(lat + lat_delta * math.cos(angle), 6),
                round(lng + lng_delta * math.sin(angle), 6),
            ],
        )
    return points


def circles_to_boundaries(apps, schema_editor):
    Municipality = apps.get_model("municipalities", "Municipality")
    for municipality in Municipality.objects.all():
        if (
            municipality.latitude is None
            or municipality.longitude is None
            or municipality.coverage_radius_km is None
        ):
            continue
        municipality.boundary = circle_to_polygon(
            municipality.latitude,
            municipality.longitude,
            municipality.coverage_radius_km,
        )
        municipality.save(update_fields=["boundary"])


def boundaries_to_circles(apps, schema_editor):
    """Vuelta atrás: el radio que cubre al polígono desde el centro guardado.

    No es el inverso exacto —un polígono trazado a mano no vuelve a ser el
    círculo del que salió— pero deja al municipio recibiendo al menos todo lo
    que recibía, que es lo que importa al revertir.
    """
    Municipality = apps.get_model("municipalities", "Municipality")
    for municipality in Municipality.objects.all():
        boundary = municipality.boundary
        if not boundary or municipality.latitude is None:
            continue
        lat = float(municipality.latitude)
        lng = float(municipality.longitude)
        furthest = max(
            math.hypot(
                (float(point[0]) - lat) * KM_PER_DEGREE,
                (float(point[1]) - lng)
                * KM_PER_DEGREE
                * max(math.cos(math.radians(lat)), 0.01),
            )
            for point in boundary
        )
        municipality.coverage_radius_km = round(furthest, 2)
        municipality.save(update_fields=["coverage_radius_km"])


class Migration(migrations.Migration):
    dependencies = [
        ("municipalities", "0002_coverage_area"),
    ]

    operations = [
        migrations.AddField(
            model_name="municipality",
            name="boundary",
            field=models.JSONField(
                blank=True,
                help_text=(
                    "Polígono del límite del municipio, como lista de pares "
                    "[latitud, longitud]. Los reportes que caen adentro le llegan."
                ),
                null=True,
                verbose_name="coverage boundary",
            ),
        ),
        migrations.RunPython(circles_to_boundaries, boundaries_to_circles),
        migrations.RemoveField(
            model_name="municipality",
            name="coverage_radius_km",
        ),
    ]
