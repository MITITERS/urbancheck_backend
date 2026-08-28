"""Permisos por rol (US-017).

Se devuelve siempre ``403`` y nunca ``404``: acá lo que falta es autorización y
el recurso no es secreto. La ocultación por jurisdicción —donde sí conviene
responder ``404``— la resuelve la capa de acceso a datos de US-034.
"""

from rest_framework.permissions import BasePermission

PANEL_DENIED_MESSAGE = (
    "Tu usuario no tiene permisos para operar el panel municipal."
)


DEACTIVATED_MESSAGE = (
    "Tu cuenta fue desactivada. Contactá al administrador de la plataforma."
)


def _operates_panel(request) -> bool:
    """Sesión válida y cuenta de trabajo habilitada.

    Los tres permisos de abajo arrancan por acá: la baja lógica de una cuenta
    tiene que cortar el acceso en todos los endpoints del panel, y dejarla en
    cada uno era garantizar que alguno se olvidara.
    """
    user = request.user
    return bool(user and user.is_authenticated and user.can_operate_panel)


class IsPlatformAdmin(BasePermission):
    """Solo el administrador de la plataforma."""

    message = PANEL_DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        return _operates_panel(request) and request.user.is_platform_admin


class IsMunicipalAgent(BasePermission):
    """Solo el agente municipal, y solo mientras su cuenta esté habilitada."""

    message = PANEL_DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        return _operates_panel(request) and request.user.is_municipal_agent


class IsPanelUser(BasePermission):
    """Cualquiera de los dos roles municipales, con la cuenta habilitada.

    Es el permiso base de todo endpoint del panel: un ciudadano o un validador
    autenticado recibe ``403``, y también lo recibe el agente dado de baja.
    """

    message = PANEL_DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        return _operates_panel(request)
