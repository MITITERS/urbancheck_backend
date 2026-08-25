"""Distancias geográficas sobre coordenadas planas (US-036 y US-037).

El modelo guarda ``latitude``/``longitude`` como decimales y el proyecto no usa
PostGIS, así que la distancia se calcula con la fórmula de Haversine. Está acá
dos veces a propósito y con la misma constante: en Python para verificar un
reporte puntual, y como expresión SQL para poder ordenar una bandeja completa
en la base en lugar de traer todo y ordenar en memoria.
"""

from __future__ import annotations

import math

from django.db.models import DecimalField
from django.db.models import F
from django.db.models import FloatField
from django.db.models import Func
from django.db.models import Value
from django.db.models.functions import ACos
from django.db.models.functions import Cast
from django.db.models.functions import Cos
from django.db.models.functions import Greatest
from django.db.models.functions import Least
from django.db.models.functions import Radians
from django.db.models.functions import Sin

EARTH_RADIUS_METERS = 6_371_000


def haversine_meters(
    lat1: float | DecimalField,
    lon1: float | DecimalField,
    lat2: float | DecimalField,
    lon2: float | DecimalField,
) -> float:
    """Distancia en metros entre dos puntos."""
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def distance_expression(latitude: float, longitude: float) -> Func:
    """Expresión SQL con la distancia de cada fila al punto dado, en metros.

    Se usa como anotación para poder ordenar por cercanía en la base. El
    argumento del ``acos`` se acota a [-1, 1]: el redondeo de punto flotante
    puede sacarlo del dominio cuando los dos puntos son casi el mismo, y ahí
    Postgres devuelve un error en vez de cero.
    """
    lat_field = Cast(F("latitude"), FloatField())
    lon_field = Cast(F("longitude"), FloatField())
    origin_lat = Radians(Value(float(latitude), output_field=FloatField()))
    origin_lon = Radians(Value(float(longitude), output_field=FloatField()))

    cosine = Cos(origin_lat) * Cos(Radians(lat_field)) * Cos(
        Radians(lon_field) - origin_lon,
    ) + Sin(origin_lat) * Sin(Radians(lat_field))

    clamped = Least(
        Greatest(cosine, Value(-1.0, output_field=FloatField())),
        Value(1.0, output_field=FloatField()),
        output_field=FloatField(),
    )
    return ACos(clamped) * Value(EARTH_RADIUS_METERS, output_field=FloatField())
