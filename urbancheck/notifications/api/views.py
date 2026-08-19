from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import DestroyModelMixin
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.notifications.models import Notification

from .serializers import NotificationSerializer


class NotificationViewSet(ListModelMixin, DestroyModelMixin, GenericViewSet):
    """Bandeja de avisos del usuario autenticado (US-009).

    El queryset se acota siempre al destinatario, así que no hace falta un permiso
    de objeto: una notificación ajena simplemente no existe para este usuario.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user).select_related(
            "actor",
        )
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Contador para el badge de la pestaña de avisos."""
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()
        return Response({"unread": count})

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        """Marca toda la bandeja como leída."""
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": updated})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        serializer = self.get_serializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)
