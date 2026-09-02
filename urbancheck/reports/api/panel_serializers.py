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
from urbancheck.reports.state_machine import VALIDATOR_DECISIONS
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.state_machine import transitions_from

from .serializers import AuthorSerializer
from .serializers import CommentSerializer


class ValidationSerializer(serializers.Serializer):
    """Qué decidió el validador que salió a mirar el reporte.

    Va junto y no como tres campos sueltos porque es una sola cosa: sin
    validador no hay fecha ni decisión, y las tres viajan o no viajan a la vez.
    """

    validator = AuthorSerializer(allow_null=True)
    decided_at = serializers.DateTimeField()
    outcome = serializers.ChoiceField(choices=sorted(set(VALIDATOR_DECISIONS.values())))


def validation_payload(entry) -> dict | None:
    """La decisión, a partir del asiento del historial que la registró."""
    if entry is None:
        return None
    return {
        "validator": AuthorSerializer(entry.changed_by).data if entry.changed_by else None,
        "decided_at": entry.created_at,
        "outcome": VALIDATOR_DECISIONS[entry.status],
    }


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
    validation = serializers.SerializerMethodField()

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
            "validation",
        ]
        read_only_fields = fields

    def get_operative_area(self, obj) -> str | None:
        return None

    @extend_schema_field(ValidationSerializer(allow_null=True))
    def get_validation(self, obj) -> dict | None:
        """Qué decidió el validador por el que se está filtrando.

        Solo viaja cuando la lista se pidió con ``?validated_by=``: es la única
        consulta en la que hay un validador del que hablar. Sin ese filtro no
        hay anotación y el campo va nulo.

        Va como ``SerializerMethodField`` y no como campo declarativo leyendo la
        anotación: un campo ``read_only`` sin su anotación se omite en silencio
        del JSON en vez de fallar, y el panel se quedaría sin saber por qué.

        El estado del reporte no reemplaza a esto: uno validado y cancelado
        después por el municipio figura como *Cancelado*, igual que uno que el
        validador rechazó.
        """
        status = getattr(obj, "validation_status", None)
        if status is None:
            return None
        return {
            # Quién es ya lo sabe quien filtró por él: no se repite por fila.
            "validator": None,
            "decided_at": getattr(obj, "validation_decided_at", None),
            "outcome": VALIDATOR_DECISIONS[status],
        }


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
    validation = serializers.SerializerMethodField()
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
            "validation",
        ]
        read_only_fields = fields

    @extend_schema_field(ValidationSerializer(allow_null=True))
    def get_validation(self, obj) -> dict | None:
        """Quién decidió sobre el reporte en terreno, y qué decidió.

        El nombre ya aparece en el historial, pero ahí está mezclado con las
        acciones del municipio y sin decir quién es cada uno. El panel necesita
        poder responder «¿quién salió a mirar esto?» sin leer la lista entera.

        Se identifica por la transición completa —desde *Pendiente de
        validación*— y no por el estado de llegada: ``reactivar`` deja el
        reporte en *Reportado* y ``cancelar`` lo deja en *Cancelado*, pero las
        ejecuta un agente desde el panel.

        Se recorre el historial ya prefetcheado, así que no agrega consultas. Se
        toma el más viejo: un reporte archivado y reactivado vuelve a pasar por
        *Reportado*, pero decidido en terreno fue una sola vez.
        """
        decisions = [
            entry
            for entry in obj.status_history.all()
            if entry.previous_status == Report.Status.PENDIENTE_VALIDACION
            and entry.status in VALIDATOR_DECISIONS
        ]
        if not decisions:
            return None
        return validation_payload(min(decisions, key=lambda entry: entry.created_at))

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
