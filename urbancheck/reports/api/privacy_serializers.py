"""Serializers de la bandeja de protección de datos del administrador (US-043)."""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.privacy import deadline_for
from urbancheck.users.models import User


class _PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email"]


class _ReportSummarySerializer(serializers.ModelSerializer):
    """El reporte denunciado: lo que hace falta para decidir sin abrirlo."""

    municipality = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "number",
            "description",
            "category",
            "status",
            "address",
            "municipality",
        ]

    def get_municipality(self, obj) -> dict:
        return {
            "id": obj.municipality_id,
            "city": obj.municipality.city,
            "province": obj.municipality.province,
        }


class _ImageSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["report", "resolution_evidence"])
    evidence_id = serializers.IntegerField(allow_null=True)
    url = serializers.CharField(allow_null=True)


class PrivacyRequestSerializer(serializers.ModelSerializer):
    """Una solicitud tal como la ve el administrador (escenarios 4, 7 y 8).

    El plazo se calcula al serializar, sobre la fecha de **recepción**: con un
    solo plazo para todas, ordenar por antigüedad ya pone primero las vencidas,
    y guardar el vencimiento en la fila lo congelaría si la configuración
    cambia.

    Para las resueltas, el tiempo restante no tiene sentido y viaja nulo; lo
    que sí viaja es si se resolvió **dentro** del plazo, que es la evidencia de
    cumplimiento de la RN-12.
    """

    received_at = serializers.DateTimeField(source="created_at", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    deadline = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    resolved_within_deadline = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    report = _ReportSummarySerializer(read_only=True)
    reporter = _PersonSerializer(read_only=True)
    resolved_by = _PersonSerializer(read_only=True)

    class Meta:
        model = ReportComplaint
        fields = [
            "id",
            "reason",
            "reason_label",
            "status",
            "received_at",
            "deadline",
            "remaining_seconds",
            "is_overdue",
            "resolved_at",
            "resolved_by",
            "resolved_within_deadline",
            "image",
            "report",
            "reporter",
        ]
        read_only_fields = fields

    def get_deadline(self, obj) -> str:
        return deadline_for(obj).isoformat()

    def get_remaining_seconds(self, obj) -> int | None:
        """Negativo si ya venció: el panel lo muestra como "vencida hace X"."""
        if not obj.is_pending:
            return None
        return int((deadline_for(obj) - timezone.now()).total_seconds())

    def get_is_overdue(self, obj) -> bool:
        return obj.is_pending and timezone.now() > deadline_for(obj)

    def get_resolved_within_deadline(self, obj) -> bool | None:
        if obj.resolved_at is None:
            return None
        return obj.resolved_at <= deadline_for(obj)

    @extend_schema_field(_ImageSerializer)
    def get_image(self, obj) -> dict:
        """La imagen denunciada, si todavía es la que se publica.

        Si se eliminó, la URL viaja nula. También si el autor la reemplazó
        mientras la solicitud esperaba: lo que se muestra entonces es otra foto,
        no la denunciada, y mostrarla como tal llevaría a decidir sobre la
        imagen equivocada.
        """
        evidence = obj.resolution_evidence
        field = evidence.photo if evidence is not None else obj.report.photo
        url = None
        if field and field.name == obj.image_name:
            request = self.context.get("request")
            url = request.build_absolute_uri(field.url) if request else field.url
        return {
            "kind": "resolution_evidence" if evidence is not None else "report",
            "evidence_id": evidence.pk if evidence is not None else None,
            "url": url,
        }
