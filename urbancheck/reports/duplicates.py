"""Detección de un reporte que ya describe el mismo problema (US-026).

Un reporte nuevo es un duplicado de otro si este es de la **misma categoría**,
de la **misma municipalidad**, está en un **estado activo** y queda a no más de
``DUPLICATE_REPORT_RADIUS_METERS`` del punto que se quiere reportar. Si hay más
de uno, el que cuenta es el más cercano.

La categoría es indispensable: en una misma esquina puede haber un bache y una
vereda rota, y son dos problemas distintos. No hay ventana de tiempo: mientras
el reclamo siga activo, el problema sigue siendo el mismo, lleve una semana o un
año.

Esta función solo detecta. Qué se hace con el resultado —rechazar el alta con un
``409`` y ofrecer sumarse— es de US-032 y vive en la vista de creación.

Todas las condiciones van en el ``WHERE``, y el índice parcial
``report_duplicate_lookup`` de ``Report`` las cubre. El proyecto no usa PostGIS,
así que la distancia es Haversine sobre las filas que dejó la caja.
"""

from __future__ import annotations

import math

from django.conf import settings

from .geo import distance_expression
from .models import Report

#: Estados en los que el problema sigue activo y conviene sumarse en vez de
#: reportarlo de nuevo.
#:
#: ``resuelto_pendiente_confirmacion`` cuenta como activo: el cierre todavía no
#: está confirmado. Si el problema sigue ahí, el reclamo existente es el lugar
#: para decirlo. Resuelto, cancelado y archivado no bloquean: un bache reparado
#: que vuelve a abrirse es un problema nuevo.
#:
#: La condición del índice ``report_duplicate_lookup`` repite esta lista; si
#: cambia, hace falta una migración que lo recree.
ACTIVE_STATUSES = (
    Report.Status.PENDIENTE_VALIDACION,
    Report.Status.REPORTADO,
    Report.Status.EN_PROCESO,
    Report.Status.RESUELTO_PENDIENTE,
)

#: Metros por grado de latitud, para el recuadro que prefiltra en la base.
_METERS_PER_DEGREE = 111_320


def radius_meters() -> int:
    """Radio vigente. Se lee en cada llamada para poder moverlo sin redeploy."""
    return settings.DUPLICATE_REPORT_RADIUS_METERS


def find_duplicate(
    *,
    category: str,
    latitude: float,
    longitude: float,
    municipality,
    queryset=None,
) -> Report | None:
    """El reporte activo más cercano que describe el mismo problema, o ``None``.

    Devuelve el reporte anotado con ``distance_meters``. ``queryset`` permite
    partir de uno ya anotado con lo que la respuesta necesite mostrar.

    Antes del Haversine se recorta por un recuadro de latitud y longitud: es
    una comparación que la base resuelve con el índice y deja al cálculo
    trigonométrico unas pocas filas. Nada se filtra en Python.
    """
    radius = radius_meters()
    lat, lng = float(latitude), float(longitude)
    delta_lat = radius / _METERS_PER_DEGREE
    delta_lng = radius / (_METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))

    base = Report.objects.all() if queryset is None else queryset
    return (
        base.filter(
            municipality=municipality,
            category=category,
            status__in=ACTIVE_STATUSES,
            # Uno retirado por protección de datos (US-043) no es visible para
            # nadie: ofrecerle al vecino sumarse a él sería mandarlo a un 404,
            # y bloquearle el alta dejaría el problema sin reportar.
            photo_removed_at__isnull=True,
            latitude__range=(lat - delta_lat, lat + delta_lat),
            longitude__range=(lng - delta_lng, lng + delta_lng),
        )
        .annotate(distance_meters=distance_expression(lat, lng))
        .filter(distance_meters__lte=radius)
        .order_by("distance_meters", "created_at")
        .first()
    )
