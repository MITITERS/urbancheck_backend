"""Permisos del rol operario (US-044, consumidos por US-045).

Dos permisos y no uno: lo que el operario **puede** —su bandeja— y lo que
deliberadamente **no** —la superficie del vecino—. Los dos delegan en una única
verificación del modelo para no terminar con criterios distintos.
"""

from rest_framework.permissions import BasePermission

CANNOT_WORK_MESSAGE = (
    "Tu cuenta de operario no está habilitada. Puede estar desactivada, o su "
    "área operativa puede haber dejado de operar: consultá con tu municipio."
)

OPERATOR_SCOPE_MESSAGE = (
    "Tu cuenta de operario accede únicamente a la bandeja de trabajo de tu "
    "área operativa."
)


class CanWorkAsOperator(BasePermission):
    """Rol operario, cuenta habilitada y área operativa activa.

    Delega en ``User.can_work_as_operator``: las tres condiciones viven en el
    modelo, igual que ``can_validate`` y ``can_operate_panel``, para que la
    bandeja y las acciones que vengan después no puedan divergir.
    """

    message = CANNOT_WORK_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.can_work_as_operator)


class ExcludesOperator(BasePermission):
    """Cierra al operario la superficie ciudadana: feed, mapa y detalle público.

    El alcance del rol es deliberadamente acotado (US-045, escenario 8): ve los
    reportes de su área y nada más. Esconderlo solo en la navegación de la app
    dejaría los endpoints abiertos, así que la restricción se aplica también acá.

    Responde ``403`` y no ``404``: al operario no le falta jurisdicción —los
    reportes son de su municipio— sino autorización, y ese es el criterio que
    separa las dos respuestas en este proyecto.
    """

    message = OPERATOR_SCOPE_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return not (user and user.is_authenticated and user.is_operator)
