"""Municipalidades: resolución de jurisdicción y baja en cascada.

Cada municipio declara el polígono de su límite y un reporte nuevo se asocia al
que lo contiene. Es el único punto del código que decide la jurisdicción de un
reporte.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from urbancheck.reports.geo import haversine_meters
from urbancheck.reports.geo import polygon_bounds

from .models import Municipality

AMBIGUOUS_MESSAGE = (
    "Hay más de una municipalidad registrada y ninguna configurada como activa. "
    "Definí DJANGO_ACTIVE_MUNICIPALITY_ID."
)
MISSING_MESSAGE = "No hay ninguna municipalidad registrada en la plataforma."
# Le habla a quien está cargando el reporte y ya sabe de qué reporte se trata:
# lo que necesita saber es que ese lugar no le corresponde a ningún municipio
# adherido, y que la salida es elegir otro punto.
OUT_OF_COVERAGE_MESSAGE = (
    "El lugar que marcaste no está dentro del área de cobertura de ninguna "
    "municipalidad adherida a UrbanCheck. Probá con una ubicación dentro de tu "
    "municipio."
)


class OutOfCoverageError(Exception):
    """El punto no cae dentro del área de ninguna municipalidad activa."""

    def __init__(self, message: str = OUT_OF_COVERAGE_MESSAGE):
        super().__init__(message)
        self.message = message


def find_covering_municipality(
    latitude: float,
    longitude: float,
) -> Municipality | None:
    """Municipalidad activa cuyo límite contiene el punto.

    Con límites bien trazados no puede haber más de una: dos municipios no
    comparten territorio. Si aun así varias lo contienen, es que alguien trazó
    mal un polígono; se desempata por centro más cercano para que el resultado
    sea determinista y no dependa del orden en que salieron de la base.

    El centro **no** decide la cobertura, solo el desempate: un municipio con
    forma de L puede tener su centroide fuera de su propio límite.
    """
    covering = [
        municipality
        for municipality in Municipality.objects.active()
        if municipality.contains(latitude, longitude)
    ]
    if not covering:
        return None
    if len(covering) == 1:
        return covering[0]
    return min(
        covering,
        key=lambda municipality: haversine_meters(
            latitude,
            longitude,
            *_reference_point(municipality),
        ),
    )


def _reference_point(municipality: Municipality) -> tuple[float, float]:
    """Punto con el que se mide la cercanía al desempatar.

    El centro guardado, que es el centroide oficial de la ciudad. Un municipio
    puede tener límite y no tenerlo —lo cargó el admin de Django, o un seed—, y
    ahí se usa el centro del recuadro del polígono: peor referencia, pero
    evita que un desempate reviente por un campo vacío.
    """
    if municipality.latitude is not None and municipality.longitude is not None:
        return float(municipality.latitude), float(municipality.longitude)
    min_lat, min_lng, max_lat, max_lng = polygon_bounds(municipality.boundary)
    return (min_lat + max_lat) / 2, (min_lng + max_lng) / 2


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


@transaction.atomic
def deactivate_municipality(municipality: Municipality) -> int:
    """Da de baja el municipio y, con él, a todo su personal.

    Un municipio dado de baja deja de recibir reportes y de operar, así que sus
    agentes y validadores no tienen nada que hacer: dejarlos habilitados sería
    dejar cuentas trabajando sobre una jurisdicción que la plataforma considera
    cerrada. La cascada vive acá y no en la vista para que valga desde cualquier
    lugar que dé de baja un municipio.

    Devuelve cuántas cuentas quedaron desactivadas, para poder decírselo a quien
    ejecutó la baja: es una consecuencia que no se ve en la pantalla desde la
    que se hace.

    **No tiene inverso automático.** Volver a dar de alta el municipio no
    reactiva a nadie: quién vuelve a trabajar es una decisión de la plataforma,
    y se toma cuenta por cuenta desde el archivado. Reactivar en bloque
    devolvería el acceso a personal que quizás ya no está.
    """
    from urbancheck.users.models import User  # noqa: PLC0415

    municipality.is_active = False
    municipality.save(update_fields=["is_active", "updated_at"])
    return User.objects.filter(
        municipality=municipality,
        role__in=User.MUNICIPALITY_BOUND_ROLES,
        is_work_account_active=True,
    ).update(is_work_account_active=False)
