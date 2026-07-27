from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission


class IsAuthorOrReadOnly(BasePermission):
    """Solo el autor puede modificar o borrar su propio objeto."""

    message = "Solo el autor puede modificar este contenido."

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        author_id = getattr(obj, "author_id", None) or getattr(obj, "user_id", None)
        return author_id == request.user.id
