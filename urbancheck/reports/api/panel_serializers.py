"""Serializers del panel municipal.

Viven aparte de los del feed ciudadano porque responden a otra pregunta: el
agente necesita gestionar, no navegar. Ninguno expone la municipalidad como
campo editable — la jurisdicción se resuelve siempre en el servidor (US-034).
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from urbancheck.municipalities.api.area_serializers import OperationalAreaSerializer
from urbancheck.municipalities.api.serializers import MunicipalitySerializer
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportAreaAssignment
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.state_machine import OFFICIAL_RESPONSE_STATUSES
from urbancheck.reports.state_machine import VALIDATOR_DECISIONS
from urbancheck.reports.state_machine import Origin
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.state_machine import transitions_from

from .serializers import AuthorSerializer
from .serializers import CommentSerializer


class AreaSummarySerializer(serializers.Serializer):
    """El área responsable, resumida para una fila o un encabezado."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class PanelOfficialResponseSerializer(serializers.ModelSerializer):
    """Una respuesta oficial vista desde el panel (US-024, escenario 12).

    Es el mismo hilo que ve el ciudadano con un dato de más: **quién** la
    publicó. La trazabilidad interna es del municipio; de cara al vecino
    responde la institución, con el mismo criterio de protección del personal
    de US-038. Por eso son dos serializers y no un campo condicional: cuál se
    usa lo decide el endpoint, no una bandera que alguien puede olvidar.
    """

    author = AuthorSerializer(read_only=True)
    municipality = MunicipalitySerializer(read_only=True)

    class Meta:
        model = OfficialResponse
        fields = ["id", "text", "created_at", "author", "municipality"]
        read_only_fields = fields


class PanelResolutionEvidenceSerializer(serializers.ModelSerializer):
    """La evidencia de resolución vista desde el panel (US-046, escenario 13).

    Es el mismo parte de trabajo que ve el ciudadano con un dato de más: **quién
    lo ejecutó**. La auditoría del trabajo es del municipio; ante el vecino
    responde el área. Por eso son dos serializers y no un campo condicional:
    cuál se usa lo decide el endpoint, no una bandera que alguien puede olvidar.
    """

    operator = AuthorSerializer(read_only=True)
    operational_area = AreaSummarySerializer(read_only=True)

    class Meta:
        model = ResolutionEvidence
        fields = [
            "id",
            "photo",
            "description",
            "created_at",
            "operator",
            "operational_area",
            "latitude",
            "longitude",
        ]
        read_only_fields = fields


class PanelResolutionAppealSerializer(serializers.ModelSerializer):
    """Una apelación del ciudadano, vista desde el panel (US-048, escenario 10).

    Lleva el vínculo con la evidencia objetada para que el agente pueda ver de
    un vistazo qué cierre se cuestionó, y con él, qué operario.
    """

    author = AuthorSerializer(read_only=True)
    evidence = PanelResolutionEvidenceSerializer(read_only=True)

    class Meta:
        model = ResolutionAppeal
        fields = ["id", "photo", "reason", "created_at", "author", "evidence"]
        read_only_fields = fields


class PanelAreaAssignmentSerializer(serializers.ModelSerializer):
    """Un asiento del registro de asignaciones de área (US-028)."""

    previous_area = AreaSummarySerializer(read_only=True)
    area = AreaSummarySerializer(read_only=True)
    assigned_by = AuthorSerializer(read_only=True)

    class Meta:
        model = ReportAreaAssignment
        fields = ["previous_area", "area", "assigned_by", "created_at"]
        read_only_fields = fields


class ValidationSerializer(serializers.Serializer):
    """Qué decidió el validador que salió a mirar el reporte.

    Va junto y no como tres campos sueltos porque es una sola cosa: sin
    validador no hay fecha ni decisión, y las tres viajan o no viajan a la vez.
    """

    validator = AuthorSerializer(allow_null=True)
    decided_at = serializers.DateTimeField()
    outcome = serializers.ChoiceField(
        choices=sorted(set(VALIDATOR_DECISIONS.values())),
    )


def validation_payload(entry) -> dict | None:
    """La decisión, a partir del asiento del historial que la registró."""
    if entry is None:
        return None
    return {
        "validator": (
            AuthorSerializer(entry.changed_by).data if entry.changed_by else None
        ),
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
    # El área responsable, para la columna del listado (US-028, escenario 11).
    operative_area = AreaSummarySerializer(source="operational_area", read_only=True)
    # Si el reporte ya recibió al menos una comunicación institucional
    # (US-024, escenario 13): es lo que deja identificar de un vistazo los
    # reclamos sin respuesta. Viaja anotado desde el queryset del panel.
    has_official_response = serializers.SerializerMethodField()
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
            "has_official_response",
            "municipality",
            "author",
            "validation",
        ]
        read_only_fields = fields

    def get_has_official_response(self, obj) -> bool:
        """Usa la anotación del queryset si está, y si no consulta.

        Mismo criterio que ``is_liked`` en el feed: un campo declarativo se
        omitiría en silencio del JSON cuando falta la anotación, y el panel se
        quedaría sin el indicador sin ninguna señal de error.
        """
        annotated = getattr(obj, "official_response_count", None)
        if annotated is not None:
            return annotated > 0
        return obj.official_responses.exists()

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
        fields = [
            "previous_status",
            "status",
            "changed_by",
            "reason",
            # De dónde salió la transición: es lo que deja distinguir una
            # validación en terreno de una colectiva, o un cierre de operario de
            # una confirmación automática (US-038).
            "origin",
            # Cuántas confirmaciones tenía al validarse colectivamente. Nulo en
            # toda otra transición (US-040, escenario 9).
            "confirmation_count",
            "created_at",
        ]
        read_only_fields = fields


class AvailableTransitionSerializer(serializers.Serializer):
    """Transición que el agente puede ejecutar ahora mismo."""

    operation = serializers.CharField()
    target = serializers.CharField()
    requires_reason = serializers.BooleanField()
    # Lo mira el panel para abrir el diálogo con el selector de área en lugar de
    # una confirmación pelada (US-028).
    requires_area = serializers.BooleanField()


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
    # El área responsable y su historia de asignaciones (US-028).
    operational_area = OperationalAreaSerializer(read_only=True)
    area_assignments = PanelAreaAssignmentSerializer(many=True, read_only=True)
    # El hilo institucional, con la identidad del agente que publicó cada
    # respuesta (US-024, escenario 12).
    official_responses = PanelOfficialResponseSerializer(many=True, read_only=True)
    can_publish_official_response = serializers.SerializerMethodField()
    # El parte de trabajo del operario y la objeción del ciudadano, con las
    # identidades que el panel sí puede auditar.
    resolution_evidences = PanelResolutionEvidenceSerializer(many=True, read_only=True)
    resolution_appeals = PanelResolutionAppealSerializer(many=True, read_only=True)
    objection_deadline = serializers.SerializerMethodField()

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
            "operational_area",
            "area_assigned_at",
            "area_assignments",
            "archived_at",
            "official_responses",
            "can_publish_official_response",
            "resolution_evidences",
            "resolution_appeals",
            "closed_at",
            "objection_deadline",
            "appeal_count",
        ]
        read_only_fields = fields

    def get_objection_deadline(self, obj) -> str | None:
        """Hasta cuándo el autor puede objetar el cierre (US-047).

        El panel lo muestra para saber cuánto falta para que el reporte se
        confirme solo, y para decidir si vale la pena confirmarlo antes.
        """
        from urbancheck.reports.resolution import objection_deadline  # noqa: PLC0415

        if obj.status != Report.Status.RESUELTO_PENDIENTE:
            return None
        deadline = objection_deadline(obj)
        return None if deadline is None else deadline.isoformat()

    def get_can_publish_official_response(self, obj) -> bool:
        """Si la acción de publicar se ofrece ahora mismo (US-024).

        Sale de la misma tabla de estados que consume el endpoint, así que el
        panel no replica la regla: dibuja el formulario si esto viene en True.
        """
        return obj.status in OFFICIAL_RESPONSE_STATUSES

    @extend_schema_field(ValidationSerializer(allow_null=True))
    def get_validation(self, obj) -> dict | None:
        """Quién decidió sobre el reporte en terreno, y qué decidió.

        El nombre ya aparece en el historial, pero ahí está mezclado con las
        acciones del municipio y sin decir quién es cada uno. El panel necesita
        poder responder «¿quién salió a mirar esto?» sin leer la lista entera.

        Se identifica por el **origen** de la transición y no por su forma.
        Mirar de dónde sale y a dónde llega no alcanza desde US-040: la
        validación colectiva también sale de *Pendiente de validación* y llega a
        *Reportado*, y ahí no hubo ningún validador que fuera al lugar. Antes
        tampoco alcanzaba con el estado de llegada solo —``reactivar`` deja el
        reporte en *Reportado* y ``cancelar`` lo deja en *Cancelado*—, y esta es
        la tercera vez que la misma forma significa cosas distintas: por eso el
        discriminador es un campo y no una deducción.

        Se recorre el historial ya prefetcheado, así que no agrega consultas. Se
        toma el más viejo: un reporte archivado y reactivado vuelve a pasar por
        *Reportado*, pero decidido en terreno fue una sola vez.
        """
        decisions = [
            entry
            for entry in obj.status_history.all()
            if entry.origin == Origin.VALIDACION_TERRENO
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
                "requires_area": transition.requires_area,
            }
            for transition in transitions_from(obj.status, Actor.MUNICIPAL_AGENT)
        ]
