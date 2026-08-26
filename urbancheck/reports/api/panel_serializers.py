"""Serializers del panel municipal.

Viven aparte de los del feed ciudadano porque responden a otra pregunta: el
agente necesita gestionar, no navegar. Ninguno expone la municipalidad como
campo editable — la jurisdicción se resuelve siempre en el servidor (US-034).
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from urbancheck.municipalities.api.serializers import MunicipalitySerializer
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.state_machine import transitions_from

from .serializers import AuthorSerializer
from .serializers import CommentSerializer


class PanelReportListSerializer(serializers.ModelSerializer):
    """Fila de la tabla del panel (US-012).

    ``municipality`` viaja siempre, aunque para el agente sea constante: es lo
    que el admin de la plataforma necesita para distinguir filas de municipios
    distintos, y una sola forma de respuesta es más fácil de sostener que dos.
    """

    author = AuthorSerializer(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    municipality = MunicipalitySerializer(read_only=True)
    # US-028 (áreas operativas) no está en este sprint: la columna existe y
    # viaja siempre nula, para que el panel no tenga que adivinar.
    operative_area = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            # Número de cara al usuario, correlativo dentro del municipio.
            "number",
            "category",
            "status",
            "created_at",
            "address",
            "latitude",
            "longitude",
            "like_count",
            "operative_area",
            "municipality",
            "author",
        ]
        read_only_fields = fields

    def get_operative_area(self, obj) -> str | None:
        return None


class PanelStatusHistorySerializer(serializers.ModelSerializer):
    """Un asiento del historial de cambios (US-013, escenario 7)."""

    changed_by = AuthorSerializer(read_only=True)

    class Meta:
        model = ReportStatusHistory
        fields = ["previous_status", "status", "changed_by", "reason", "created_at"]
        read_only_fields = fields


class AvailableTransitionSerializer(serializers.Serializer):
    """Transición que el agente puede ejecutar ahora mismo."""

    operation = serializers.CharField()
    target = serializers.CharField()
    requires_reason = serializers.BooleanField()


class PanelReportDetailSerializer(serializers.ModelSerializer):
    """Detalle del reporte en el panel, con su historial y sus acciones.

    ``available_transitions`` viaja calculado desde la máquina de estados: el
    panel renderiza solo lo que se puede hacer en lugar de dibujar cinco botones
    y deshabilitar cuatro, y la lógica de transiciones sigue viviendo en un solo
    lado.
    """

    author = AuthorSerializer(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    status_history = PanelStatusHistorySerializer(many=True, read_only=True)
    available_transitions = serializers.SerializerMethodField()
    # La necesita el panel para saber a dónde vuelve el administrador, que llega
    # al detalle desde la ficha de una municipalidad y no desde un listado.
    municipality = MunicipalitySerializer(read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            # Número de cara al usuario, correlativo dentro del municipio.
            "number",
            "photo",
            "description",
            "category",
            "status",
            "address",
            "latitude",
            "longitude",
            "created_at",
            "updated_at",
            "municipality",
            "author",
            "like_count",
            "comments",
            "status_history",
            "available_transitions",
        ]
        read_only_fields = fields

    @extend_schema_field(AvailableTransitionSerializer(many=True))
    def get_available_transitions(self, obj) -> list[dict]:
        return [
            {
                "operation": transition.operation,
                "target": transition.target,
                "requires_reason": transition.requires_reason,
            }
            for transition in transitions_from(obj.status, Actor.MUNICIPAL_AGENT)
        ]
