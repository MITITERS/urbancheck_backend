"""Serializers de la moderación municipal de contenido (US-049)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from urbancheck.municipalities.api.serializers import MunicipalitySerializer
from urbancheck.reports.models import ModerationDecision
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.models import ResolutionAppeal

from .panel_serializers import PanelComplaintSerializer
from .serializers import AuthorSerializer


def panel_photo_url(report: Report, request) -> str | None:
    """La imagen del reporte para la pantalla de Denuncias del panel.

    Va aunque esté retenida por una denuncia de dato personal: desde el 21/10
    el agente y el admin ven esas imágenes para resolverlas, y la misma foto no
    puede verse en una fila y faltar en la de al lado.
    """
    if not report.photo:
        return None
    url = report.photo.url
    return request.build_absolute_uri(url) if request else url


class ModerationReasonSerializer(serializers.Serializer):
    """El motivo de la decisión: obligatorio en los dos sentidos (escenario 5)."""

    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class ModerationInboxEntrySerializer(serializers.ModelSerializer):
    """Una entrada de la bandeja: **un reporte**, con todas sus denuncias.

    Varias denuncias sobre el mismo reporte se resuelven en una sola decisión
    (escenario 2), así que la bandeja agrupa por reporte. ``complaints`` trae
    solo las pendientes por contenido —las de dato personal nunca entran—, ya
    prefetcheadas por la vista.
    """

    complaints = serializers.SerializerMethodField()
    pending_complaint_count = serializers.IntegerField(read_only=True)
    oldest_complaint_at = serializers.DateTimeField(read_only=True)
    author = AuthorSerializer(read_only=True)
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "number",
            "category",
            "status",
            "description",
            "address",
            "photo",
            "created_at",
            "author",
            "pending_complaint_count",
            "oldest_complaint_at",
            "complaints",
        ]
        read_only_fields = fields

    @extend_schema_field(PanelComplaintSerializer(many=True))
    def get_complaints(self, obj) -> list[dict]:
        return PanelComplaintSerializer(obj.pending_content_complaints, many=True).data

    def get_photo(self, obj) -> str | None:
        return panel_photo_url(obj, self.context.get("request"))


class ModerationDecisionSerializer(serializers.ModelSerializer):
    decided_by = AuthorSerializer(read_only=True)

    class Meta:
        model = ModerationDecision
        fields = [
            "id",
            "outcome",
            "reason",
            "previous_status",
            "decided_by",
            "created_at",
        ]
        read_only_fields = fields


class _AppealReportSerializer(serializers.ModelSerializer):
    """El reporte apelado, con lo necesario para juzgarlo sin abrirlo: la foto,
    qué dice y dónde está."""

    municipality = MunicipalitySerializer(read_only=True)
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "number",
            "category",
            "status",
            "description",
            "address",
            "photo",
            "created_at",
            "municipality",
        ]
        read_only_fields = fields

    def get_photo(self, obj) -> str | None:
        return panel_photo_url(obj, self.context.get("request"))


class ResolvedModerationSerializer(serializers.ModelSerializer):
    """Una decisión ya tomada sobre denuncias por contenido: la pestaña
    «Resueltas» de Denuncias, el registro equivalente al de dato personal.

    ``received_at`` es la denuncia más vieja que cerró, anotada por la vista.
    """

    decided_by = AuthorSerializer(read_only=True)
    reverted_by = AuthorSerializer(read_only=True)
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    received_at = serializers.DateTimeField(read_only=True)
    report = _AppealReportSerializer(read_only=True)
    complaints = PanelComplaintSerializer(many=True, read_only=True)

    class Meta:
        model = ModerationDecision
        fields = [
            "id",
            "outcome",
            "outcome_label",
            "reason",
            "decided_by",
            "created_at",
            "reverted_at",
            "reverted_by",
            "received_at",
            "report",
            "complaints",
        ]
        read_only_fields = fields


class ModerationAppealSerializer(serializers.ModelSerializer):
    """Una apelación contra un descarte, tal como la ve el administrador.

    Lleva lo que necesita para decidir sin abrir el reporte: el descarte que se
    apela, con el motivo del agente, y las denuncias que lo provocaron.
    """

    author = AuthorSerializer(read_only=True)
    resolved_by = AuthorSerializer(read_only=True)
    report = _AppealReportSerializer(read_only=True)
    decision = ModerationDecisionSerializer(
        source="moderation_decision",
        read_only=True,
    )
    complaints = serializers.SerializerMethodField()

    class Meta:
        model = ResolutionAppeal
        fields = [
            "id",
            "status",
            "reason",
            "created_at",
            "resolved_at",
            "resolved_by",
            "resolution_reason",
            "author",
            "report",
            "decision",
            "complaints",
        ]
        read_only_fields = fields

    @extend_schema_field(PanelComplaintSerializer(many=True))
    def get_complaints(self, obj) -> list[dict]:
        complaints = ReportComplaint.objects.filter(
            moderation_decision=obj.moderation_decision_id,
        ).select_related("reporter")
        return PanelComplaintSerializer(complaints, many=True).data
