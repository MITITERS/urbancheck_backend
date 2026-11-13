"""Permiso de capacidad de validación (US-035, consumido por US-036 y US-037)."""

from rest_framework.permissions import BasePermission

CANNOT_VALIDATE_MESSAGE = (
    "Tu usuario no está habilitado para validar reportes en terreno."
)


class CanValidate(BasePermission):
    """Delega en la verificación única del modelo: rol, alta lógica y contraseña.

    No repite las tres condiciones acá: si se duplicaran, US-036 y US-037
    terminarían con criterios distintos.
    """

    message = CANNOT_VALIDATE_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.can_validate)
