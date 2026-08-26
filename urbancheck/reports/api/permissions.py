from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission

CANNOT_PARTICIPATE_MESSAGE = (
    "Tu cuenta es de trabajo y no participa como vecino. "
    "Para reportar, comentar o dar me gusta, usá una cuenta personal."
)


class IsAuthorOrReadOnly(BasePermission):
    """Solo el autor puede modificar o borrar su propio objeto."""

    message = "Solo el autor puede modificar este contenido."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        author_id = getattr(obj, "author_id", None) or getattr(obj, "user_id", None)
        return author_id == request.user.id


class ParticipatesAsCitizen(BasePermission):
    """Reportar, comentar y dar me gusta: solo las cuentas de vecino.

    Delega en la verificación única del modelo en lugar de mirar el rol acá,
    por el mismo motivo que ``CanValidate``: si la regla se duplica, las dos
    copias terminan divergiendo.
    """

    message = CANNOT_PARTICIPATE_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.participates_as_citizen)
