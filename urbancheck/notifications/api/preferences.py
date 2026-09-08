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
#:
#: Un tipo sin entrada acá cae en "otros" y aparece igual —el catálogo se deriva
#: de ``Notification.Kind``, no de este diccionario—, pero agrupado con el resto
#: de los huérfanos y sin descripción. Al sumar un tipo, sumarlo también acá.
GROUPS = {
    Notification.Kind.NUEVO_COMENTARIO: "social",
    Notification.Kind.NUEVO_LIKE: "social",
    Notification.Kind.CAMBIO_ESTADO: "estado",
    # Todo lo que es el municipio hablándole al vecino sobre su reporte va con
    # el avance: para quien lo recibe es la misma conversación.
    Notification.Kind.RESPUESTA_OFICIAL: "estado",
    Notification.Kind.PROXIMO_ARCHIVADO: "estado",
    Notification.Kind.PROXIMA_CONFIRMACION: "estado",
    # Este no le llega al vecino sino al personal municipal: es trabajo, no
    # avance de un reclamo propio.
    Notification.Kind.APELACION_CIERRE: "trabajo",
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
    Notification.Kind.RESPUESTA_OFICIAL: (
        "Cuando el municipio publica una comunicación oficial sobre tu reporte."
    ),
    Notification.Kind.PROXIMO_ARCHIVADO: (
        "Cuando tu reporte está por archivarse porque no logró validarse."
    ),
    Notification.Kind.PROXIMA_CONFIRMACION: (
        "Cuando está por vencer el plazo para objetar la resolución de tu reporte."
    ),
    Notification.Kind.APELACION_CIERRE: (
        "Cuando un vecino objeta el cierre de un reporte de tu área."
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
