"""Permisos por rol (US-017).

Se devuelve siempre ``403`` y nunca ``404``: acá lo que falta es autorización y
el recurso no es secreto. La ocultación por jurisdicción —donde sí conviene
responder ``404``— la resuelve la capa de acceso a datos de US-034.
"""

from rest_framework.permissions import BasePermission

PANEL_DENIED_MESSAGE = (
    "Tu usuario no tiene permisos para operar el panel municipal."
)


class IsPlatformAdmin(BasePermission):
    """Solo el administrador de la plataforma."""

    message = PANEL_DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_platform_admin)


class IsMunicipalAgent(BasePermission):
    """Solo el agente municipal."""

    message = PANEL_DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_municipal_agent)


class IsPanelUser(BasePermission):
    """Cualquiera de los dos roles municipales.

    Es el permiso base de todo endpoint del panel: un ciudadano o un validador
    autenticado recibe ``403``.
    """

    message = PANEL_DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_panel_user)
