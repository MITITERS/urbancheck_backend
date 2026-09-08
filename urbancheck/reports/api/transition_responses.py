"""Traducción de errores de transición a respuestas HTTP.

Compartida por el panel (US-013) y por la validación en terreno (US-036), para
que la misma situación no responda distinto según el endpoint.
"""

from rest_framework import status as http_status
from rest_framework.response import Response

from urbancheck.reports.services import AreaRequiredError
from urbancheck.reports.services import ReasonRequiredError
from urbancheck.reports.services import TransitionError

#: Errores que son un dato que falta en el formulario y no un desfasaje de
#: estado. Los dos se corrigen completando la acción, así que responden ``400``.
FORM_ERRORS = (ReasonRequiredError, AreaRequiredError)


def transition_error_response(error: TransitionError) -> Response:
    """``400`` si falta el motivo o el área; ``409`` si la transición no aplica.

    Un dato ausente es un problema del formulario; una transición que no
    aplica significa que la vista del cliente está desactualizada, y por eso la
    respuesta incluye el estado actual y las transiciones disponibles.
    """
    code = (
        http_status.HTTP_400_BAD_REQUEST
        if isinstance(error, FORM_ERRORS)
        else http_status.HTTP_409_CONFLICT
    )
    return Response(
        {
            "detail": error.message,
            "current_status": error.current_status,
            "available_transitions": list(error.available),
        },
        status=code,
    )
