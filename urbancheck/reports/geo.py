"""Geometría sobre coordenadas planas (US-036, US-037 y áreas de cobertura).

El modelo guarda ``latitude``/``longitude`` como decimales y el proyecto no usa
PostGIS, así que todo se resuelve a mano.

La distancia usa Haversine y está acá dos veces a propósito, con la misma
constante: en Python para verificar un reporte puntual, y como expresión SQL
para poder ordenar una bandeja completa en la base en lugar de traer todo y
ordenar en memoria.

La pertenencia a un área de cobertura es punto-en-polígono por lanzamiento de
rayo. Se hace en Python y no en SQL porque sin PostGIS no hay forma de
expresarla como consulta; a la escala de este sistema —decenas de municipios—
el costo es despreciable, y ``polygon_bounds`` da el recuadro con el que sí se
puede filtrar en la base cuando hace falta.
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
METERS_PER_KM = 1000

#: Un polígono necesita al menos un triángulo para encerrar área.
MIN_BOUNDARY_POINTS = 3


def parse_coordinates(data) -> tuple[float, float] | None:
    """Lee ``latitude``/``longitude`` de un dict de request. ``None`` si faltan.

    Sirve tanto para un cuerpo JSON como para ``query_params``. Un valor
    ilegible se trata como ausente y nunca como un 400: la pantalla que manda
    la ubicación tiene que seguir funcionando sin ella.
    """
    try:
        return float(data["latitude"]), float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


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


def polygon_bounds(boundary) -> tuple[float, float, float, float]:
    """Recuadro que contiene al polígono: ``(min_lat, min_lng, max_lat, max_lng)``.

    Sirve para dos cosas: descartar rápido un punto que ni siquiera está cerca,
    y armar un filtro de base para los casos en los que hay que recortar un
    queryset sin poder ejecutar punto-en-polígono en SQL.
    """
    latitudes = [float(point[0]) for point in boundary]
    longitudes = [float(point[1]) for point in boundary]
    return min(latitudes), min(longitudes), max(latitudes), max(longitudes)


def point_in_polygon(latitude: float, longitude: float, boundary) -> bool:
    """Si el punto cae dentro del polígono, por lanzamiento de rayo.

    ``boundary`` es una lista de pares ``[lat, lng]``. El polígono se considera
    cerrado: no hace falta repetir el primer punto al final.

    El algoritmo tira un rayo horizontal desde el punto y cuenta cuántos lados
    cruza; impar significa adentro. Un punto exactamente sobre un lado queda
    indefinido —puede dar dentro o fuera según de qué lado se lo mire—, y eso
    es aceptable: hablamos de milímetros sobre el borde de un municipio.

    A esta escala la curvatura de la Tierra no cambia el resultado, así que se
    trabaja sobre lat/lng como si fueran un plano.
    """
    if not boundary or len(boundary) < MIN_BOUNDARY_POINTS:
        return False

    min_lat, min_lng, max_lat, max_lng = polygon_bounds(boundary)
    if not (min_lat <= latitude <= max_lat and min_lng <= longitude <= max_lng):
        return False

    inside = False
    count = len(boundary)
    previous = count - 1
    for current in range(count):
        lat_current, lng_current = (
            float(boundary[current][0]),
            float(boundary[current][1]),
        )
        lat_previous, lng_previous = (
            float(boundary[previous][0]),
            float(boundary[previous][1]),
        )
        # El rayo solo puede cruzar este lado si el lado abarca la latitud del
        # punto. La comparación asimétrica —un extremo estricto y el otro no—
        # es lo que evita contar dos veces un vértice a la altura exacta.
        if (lat_current > latitude) != (lat_previous > latitude):
            crossing_lng = lng_current + (latitude - lat_current) * (
                lng_previous - lng_current
            ) / (lat_previous - lat_current)
            if longitude < crossing_lng:
                inside = not inside
        previous = current
    return inside
