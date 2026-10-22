"""La página pública de un reporte compartido (US-030).

``GET /api/public/reports/<token>/`` es el **único** endpoint de la API que
responde sin sesión. Lo consume la ruta pública del panel, ``/r/<token>``, que es
a donde llega quien abre el enlace sin tener la app.

Lo que muestra lo decide la función única de visibilidad: un reporte que no es
público —cancelado, archivado, retirado por protección de datos, con la imagen
en proceso— responde ``404`` con ``code: report_unavailable``, igual que si no
existiera (escenario 3). La excepción es el descarte por moderación (US-049):
ahí el ``404`` lleva el motivo, que es público.

Se busca por ``share_token`` y nunca por id: el id es correlativo, y con él se
podrían recorrer todos los reportes cambiando un número.
"""

from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from urbancheck.common.throttling import ScopedThrottle
from urbancheck.reports.models import Report

from .serializers import moderation_payload

UNAVAILABLE_CODE = "report_unavailable"
UNAVAILABLE_MESSAGE = "Este reporte ya no está disponible."


def share_url_for(report: Report) -> str:
    return settings.PUBLIC_REPORT_URL.format(token=report.share_token)


class _TimelineEntrySerializer(serializers.Serializer):
    status = serializers.CharField()
    status_label = serializers.CharField()
    created_at = serializers.DateTimeField()


class _OfficialResponseSerializer(serializers.Serializer):
    text = serializers.CharField()
    created_at = serializers.DateTimeField()


class PublicReportSerializer(serializers.ModelSerializer):
    """El reporte tal como lo ve cualquiera que abre el enlace (escenario 2).

    Todo lo que muestra el detalle de la app a un vecino, sin lo que identifica a
    personas: no viaja el autor, ni quién validó o cerró, ni los comentarios.
    Responde el municipio, como en la app (US-024). La foto es la difuminada:
    un reporte con la imagen sin procesar no llega acá.
    """

    category_label = serializers.CharField(source="get_category_display")
    status_label = serializers.CharField(source="get_status_display")
    municipality = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    official_responses = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "number",
            "category",
            "category_label",
            "status",
            "status_label",
            "description",
            "photo",
            "address",
            "latitude",
            "longitude",
            "created_at",
            "municipality",
            "like_count",
            "timeline",
            "official_responses",
            "share_url",
        ]
        read_only_fields = fields

    def get_municipality(self, obj) -> dict:
        return {"city": obj.municipality.city, "province": obj.municipality.province}

    def get_like_count(self, obj) -> int:
        return obj.likes.count()

    @extend_schema_field(_TimelineEntrySerializer(many=True))
    def get_timeline(self, obj) -> list[dict]:
        labels = dict(Report.Status.choices)
        entries = obj.status_history.order_by("created_at")
        return [
            {
                "status": entry.status,
                "status_label": labels.get(entry.status, entry.status),
                "created_at": entry.created_at,
            }
            for entry in entries
        ]

    @extend_schema_field(_OfficialResponseSerializer(many=True))
    def get_official_responses(self, obj) -> list[dict]:
        return [
            {"text": response.text, "created_at": response.created_at}
            for response in obj.official_responses.order_by("created_at")
        ]

    def get_share_url(self, obj) -> str:
        return share_url_for(obj)


class PublicReportView(APIView):
    permission_classes = [AllowAny]

    def get_throttles(self):
        return [ScopedThrottle("public_reports")]

    @extend_schema(responses={200: PublicReportSerializer})
    def get(self, request, token):
        report = (
            Report.objects.publicly_visible()
            .select_related("municipality")
            .filter(share_token=token)
            .first()
        )
        if report is not None:
            return Response(
                PublicReportSerializer(report, context={"request": request}).data,
            )
        notice = Report.objects.moderation_notices().filter(share_token=token).first()
        return Response(
            {
                "code": UNAVAILABLE_CODE,
                "detail": UNAVAILABLE_MESSAGE,
                # Descartado por moderación: el motivo es público (US-049).
                "moderation": (
                    moderation_payload(notice, request=None) if notice else None
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
