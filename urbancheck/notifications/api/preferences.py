"""Preferencias de notificaciones del usuario (US-025).

El catálogo de tipos se deriva de ``Notification.Kind``: si aparece un tipo
nuevo, aparece solo en la pantalla de configuración, sin tocar este archivo.
"""

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from urbancheck.notifications.models import Notification
from urbancheck.notifications.models import NotificationPreference

#: Agrupación para que la pantalla pueda separar los avisos por categoría.
GROUPS = {
    Notification.Kind.NUEVO_COMENTARIO: "social",
    Notification.Kind.NUEVO_LIKE: "social",
    Notification.Kind.CAMBIO_ESTADO: "estado",
}

INVALID_PAYLOAD_MESSAGE = (
    "Indicá un tipo de notificación válido y un valor booleano."
)

DESCRIPTIONS = {
    Notification.Kind.NUEVO_COMENTARIO: "Cuando alguien comenta uno de tus reportes.",
    Notification.Kind.NUEVO_LIKE: "Cuando alguien apoya uno de tus reportes.",
    Notification.Kind.CAMBIO_ESTADO: (
        "Cuando tu reporte avanza: validado, en gestión, resuelto o cancelado."
    ),
}


class NotificationPreferenceSerializer(serializers.Serializer):
    kind = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    group = serializers.CharField(read_only=True)
    enabled = serializers.BooleanField()


class NotificationPreferenceView(APIView):
    """``GET`` devuelve el catálogo completo; ``PATCH`` cambia un tipo."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        stored = {
            preference.kind: preference.enabled
            for preference in NotificationPreference.objects.filter(user=request.user)
        }
        # El default es "todo activado": la ausencia de fila significa
        # habilitado, y por eso la pantalla puede listar el catálogo entero sin
        # que el usuario tenga preferencias creadas.
        data = [
            {
                "kind": kind,
                "label": label,
                "description": DESCRIPTIONS.get(kind, ""),
                "group": GROUPS.get(kind, "otros"),
                "enabled": stored.get(kind, True),
            }
            for kind, label in Notification.Kind.choices
        ]
        return Response(NotificationPreferenceSerializer(data, many=True).data)

    def patch(self, request):
        kind = request.data.get("kind")
        enabled = request.data.get("enabled")
        valid_kinds = set(Notification.Kind.values)
        if kind not in valid_kinds or not isinstance(enabled, bool):
            return Response({"detail": INVALID_PAYLOAD_MESSAGE}, status=400)

        NotificationPreference.objects.update_or_create(
            user=request.user,
            kind=kind,
            defaults={"enabled": enabled},
        )
        return self.get(request)
