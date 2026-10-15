"""Límites de tasa de la API por alcance (deuda de seguridad del Sprint 4).

``ScopedRateThrottle`` de DRF toma un único alcance por vista, y acá una misma
vista —``ReportViewSet``— atiende acciones con límites distintos: crear un
reporte, comentar, denunciar. ``ScopedThrottle`` recibe el alcance al
construirse, y cada vista decide en ``get_throttles`` cuáles le tocan a la
acción en curso. Una acción puede consumir más de uno: una denuncia por dato
personal cuenta como denuncia **y** como solicitud por dato personal, para que
no se pueda esquivar uno de los dos límites eligiendo el otro endpoint.

Los valores viven en ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` y salen de
variables de entorno. El contador es por usuario autenticado; sin sesión, por
IP, con la misma cuenta de proxies que el resto del sistema.
"""

from __future__ import annotations

import math

from rest_framework.exceptions import Throttled
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import exception_handler

THROTTLED_CODE = "throttled"


class ScopedThrottle(SimpleRateThrottle):
    def __init__(self, scope: str):
        # ``SimpleRateThrottle.__init__`` lee la tasa a partir de ``scope``.
        self.scope = scope
        # DRF guarda las tasas como atributo de clase al importar el módulo, y
        # desde ahí ya no ve un cambio de configuración. Como el resto de los
        # parámetros, la tasa se lee en cada evaluación.
        self.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
        super().__init__()

    def get_cache_key(self, request, view) -> str:
        user = request.user
        ident = user.pk if user and user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


def throttled_message(wait: float | None) -> str:
    if not wait:
        return "Hiciste demasiadas solicitudes seguidas. Probá de nuevo más tarde."
    minutes = math.ceil(wait / 60)
    if minutes <= 1:
        return "Hiciste demasiadas solicitudes seguidas. Probá de nuevo en un minuto."
    when = (
        f"{minutes} minutos"
        if minutes < 120  # noqa: PLR2004
        else f"{math.ceil(minutes / 60)} horas"
    )
    return f"Hiciste demasiadas solicitudes seguidas. Probá de nuevo en {when}."


def api_exception_handler(exc, context):
    """El de DRF, con el ``429`` en castellano y con un código estable.

    El cliente mira ``code`` para elegir el mensaje, igual que con los ``409``
    del dominio; ``retry_after`` repite la cabecera ``Retry-After`` en el
    cuerpo para quien no la lea.
    """
    response = exception_handler(exc, context)
    if isinstance(exc, Throttled) and response is not None:
        response.data = {
            "code": THROTTLED_CODE,
            "detail": throttled_message(exc.wait),
            "retry_after": math.ceil(exc.wait) if exc.wait else None,
        }
    return response
