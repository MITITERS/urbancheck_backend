from rest_framework import serializers

from urbancheck.notifications.models import Notification
from urbancheck.reports.api.serializers import AuthorSerializer


class NotificationSerializer(serializers.ModelSerializer):
    actor = AuthorSerializer(read_only=True)
    # El cliente navega al detalle del reporte con este id.
    report_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "actor",
            "report_id",
            "message",
            # Detalle del cambio de estado; vacío en los avisos sociales.
            "previous_status",
            "new_status",
            "reason",
            "is_read",
            "created_at",
        ]
        read_only_fields = fields
