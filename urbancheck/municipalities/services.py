"""Resolución de la municipalidad de un reporte (US-034, revisada).

Cada municipio declara un área de cobertura circular —centro y radio— y un
reporte nuevo se asocia al que lo cubre. Es el único punto del código que decide
la jurisdicción de un reporte: cuando llegue la resolución por polígonos reales,
se reemplaza el cuerpo de estas funciones y nada más.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from urbancheck.reports.geo import haversine_meters

from .models import Municipality

AMBIGUOUS_MESSAGE = (
    "Hay más de una municipalidad registrada y ninguna configurada como activa. "
    "Definí DJANGO_ACTIVE_MUNICIPALITY_ID."
)
MISSING_MESSAGE = "No hay ninguna municipalidad registrada en la plataforma."
OUT_OF_COVERAGE_MESSAGE = (
    "La ubicación del reporte está fuera del área de cobertura de las "
    "municipalidades registradas."
)

METERS_PER_KM = 1000


class OutOfCoverageError(Exception):
    """El punto no cae dentro del radio de ninguna municipalidad activa."""

    def __init__(self, message: str = OUT_OF_COVERAGE_MESSAGE):
        super().__init__(message)
        self.message = message


def find_covering_municipality(
    latitude: float,
    longitude: float,
) -> Municipality | None:
    """Municipalidad activa cuya área de cobertura contiene el punto.

    Si varias lo cubren —áreas superpuestas—, gana la de centro más cercano: es
    la que con más probabilidad tiene competencia real sobre ese lugar.
    """
    candidates = [
        (
            haversine_meters(
                latitude,
                longitude,
                municipality.latitude,
                municipality.longitude,
            ),
            municipality,
        )
        for municipality in Municipality.objects.active()
        if municipality.has_coverage
    ]
    covering = [
        (distance, municipality)
        for distance, municipality in candidates
        if distance <= float(municipality.coverage_radius_km) * METERS_PER_KM
    ]
    if not covering:
        return None
    return min(covering, key=lambda item: item[0])[1]


def get_active_municipality() -> Municipality:
    """Municipalidad de respaldo para un reporte **sin coordenadas**.

    Solo se llega acá cuando el reporte no tiene ubicación —el ciudadano escribió
    una dirección y la geocodificación falló—, así que no hay punto contra el
    cual evaluar cobertura. Se usa la configurada en ``ACTIVE_MUNICIPALITY_ID``
    o, si hay una sola registrada, esa.
    """
    configured_id = getattr(settings, "ACTIVE_MUNICIPALITY_ID", None)
    if configured_id:
        return Municipality.objects.get(pk=configured_id)

    municipalities = list(Municipality.objects.active()[:2])
    if not municipalities:
        raise ImproperlyConfigured(MISSING_MESSAGE)
    if len(municipalities) > 1:
        raise ImproperlyConfigured(AMBIGUOUS_MESSAGE)
    return municipalities[0]


def resolve_municipality_for(
    latitude: float | None,
    longitude: float | None,
) -> Municipality:
    """Municipalidad a la que pertenece un reporte creado en ese punto.

    Con coordenadas, manda la cobertura: si ninguna municipalidad cubre el
    lugar, la operación se rechaza en vez de asignarlo a cualquiera. Sin
    coordenadas no hay cobertura que evaluar y se cae al respaldo.
    """
    if latitude is None or longitude is None:
        return get_active_municipality()

    municipality = find_covering_municipality(float(latitude), float(longitude))
    if municipality is None:
        raise OutOfCoverageError
    return municipality
