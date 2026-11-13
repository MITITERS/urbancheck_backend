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
podrían recorrer todos los reportes cambiando un número. Por lo mismo, la
respuesta no lo incluye, y las coordenadas van redondeadas (N-06). La app, que
con sesión abre el detalle, resuelve el token con ``SharedReportResolveView``.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from urbancheck.common.throttling import ScopedThrottle
from urbancheck.reports.models import Report

from .serializers import moderation_payload

UNAVAILABLE_CODE = "report_unavailable"
UNAVAILABLE_MESSAGE = "Este reporte ya no está disponible."


def share_url_for(report: Report) -> str:
    return settings.PUBLIC_REPORT_URL.format(token=report.share_token)


def rounded_coordinate(value: Decimal | None) -> str | None:
    """La coordenada con ``PUBLIC_COORDINATE_DECIMALS`` decimales (N-06).

    Con 3, unos 100 m: alcanza para ubicar el problema en el mapa sin marcar la
    puerta de quien lo reportó.
    """
    if value is None:
        return None
    return str(value.quantize(Decimal(1).scaleb(-settings.PUBLIC_COORDINATE_DECIMALS)))


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
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    class Meta:
        model = Report
        # Sin ``id`` (N-06): es correlativo. El número es por municipio.
        fields = [
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

    def get_latitude(self, obj) -> str | None:
        return rounded_coordinate(obj.latitude)

    def get_longitude(self, obj) -> str | None:
        return rounded_coordinate(obj.longitude)

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


class SharedReportResolveView(APIView):
    """El id del reporte de un enlace compartido, para la app con sesión.

    La respuesta pública ya no lleva el id (N-06); la app lo necesita para
    abrir el detalle. Pide sesión y aplica la misma visibilidad que la página
    pública: lo que no es público responde ``404``.
    """

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [ScopedThrottle("public_reports")]

    @extend_schema(
        responses={
            200: inline_serializer(
                "SharedReportId",
                {"id": serializers.IntegerField()},
            ),
        },
    )
    def get(self, request, token):
        report_id = (
            Report.objects.publicly_visible()
            .filter(share_token=token)
            .values_list("pk", flat=True)
            .first()
        )
        if report_id is None:
            return Response(
                {"code": UNAVAILABLE_CODE, "detail": UNAVAILABLE_MESSAGE},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"id": report_id})
