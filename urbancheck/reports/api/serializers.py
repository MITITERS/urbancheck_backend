from rest_framework import serializers

from urbancheck.common.fields import LatitudeField
from urbancheck.common.fields import LongitudeField
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.users.models import User


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "avatar"]


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = AuthorSerializer(read_only=True)

    class Meta:
        model = ReportStatusHistory
        fields = ["status", "created_at", "changed_by"]


class ResolutionEvidenceSerializer(serializers.ModelSerializer):
    """La evidencia de resolución tal como la ve el ciudadano (US-046).

    Muestra **el área operativa**, la fecha y el trabajo descrito, pero no quién
    lo hizo: es el mismo criterio de protección del personal municipal que
    US-038 aplica al validador y US-024 al agente. La identidad del operario se
    ve únicamente en el panel, y por eso son dos serializers y no uno con un
    flag que decide el cliente.
    """

    operational_area = serializers.SerializerMethodField()

    class Meta:
        model = ResolutionEvidence
        fields = ["id", "photo", "description", "created_at", "operational_area"]
        read_only_fields = fields

    def get_operational_area(self, obj) -> str | None:
        if obj.operational_area_id is None:
            return None
        return obj.operational_area.name


class ResolutionAppealSerializer(serializers.ModelSerializer):
    """Una apelación del autor, en el hilo del reporte (US-048).

    El autor de la apelación es siempre el autor del reporte, que ya viaja en el
    detalle: repetirlo acá no agrega nada.
    """

    class Meta:
        model = ResolutionAppeal
        fields = ["id", "photo", "reason", "created_at"]
        read_only_fields = fields


class ResolutionCreateSerializer(serializers.Serializer):
    """El parte de trabajo que sube el operario al cerrar (US-046).

    Los tres campos son obligatorios y por motivos distintos: sin foto no hay
    evidencia de que el trabajo se hizo, sin descripción no se sabe qué se hizo,
    y sin coordenadas no se puede verificar que quien cierra estuvo en el lugar.

    Es un ``Serializer`` y no un ``ModelSerializer`` porque lo que recibe no es
    la evidencia entera: el operario, el área y el reporte los pone el servidor.
    """

    photo = serializers.ImageField()
    description = serializers.CharField(allow_blank=False, trim_whitespace=True)
    latitude = LatitudeField()
    longitude = LongitudeField()


class ResolutionAppealCreateSerializer(serializers.Serializer):
    """La objeción del autor al cierre (US-048).

    Motivo y foto son obligatorios: una apelación sin evidencia no se distingue
    de una objeción caprichosa y no reabre trabajo municipal.
    """

    photo = serializers.ImageField()
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class OfficialResponseSerializer(serializers.ModelSerializer):
    """Una respuesta oficial tal como la ve el ciudadano (US-024).

    Responde la **municipalidad**, no la persona: el encabezado lleva el nombre
    del municipio y la fecha, y la identidad individual del agente no viaja acá.
    Es el mismo criterio de protección del personal que US-038 aplica al
    validador, y por eso el panel usa su propio serializer en vez de un campo
    que se muestre o no según quién pregunte.
    """

    municipality = serializers.SerializerMethodField()

    class Meta:
        model = OfficialResponse
        fields = ["id", "text", "created_at", "municipality"]
        read_only_fields = fields

    def get_municipality(self, obj) -> str:
        return obj.municipality.city


class OfficialResponseCreateSerializer(serializers.ModelSerializer):
    """Publicación de una respuesta oficial (US-024).

    Solo recibe el texto. El reporte lo fija la URL, el autor sale de la sesión
    y la municipalidad se deriva del reporte: ninguno de los tres se acepta del
    cliente.

    **No hay serializer de actualización**, a propósito: el hilo es inmutable y
    esa garantía se sostiene en la ausencia de la operación, no en una
    validación que después alguien puede relajar.
    """

    class Meta:
        model = OfficialResponse
        fields = ["id", "text", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "text": {
                "allow_blank": False,
                "trim_whitespace": True,
                "max_length": OfficialResponse.MAX_LENGTH,
            },
        }


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    is_mine = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "author", "text", "created_at", "is_mine", "can_delete"]
        read_only_fields = ["id", "author", "created_at"]

    def get_is_mine(self, obj) -> bool:
        """Si lo escribió quien está mirando: sirve para distinguirlo a la vista."""
        request = self.context.get("request")
        return bool(request and obj.author_id == request.user.id)

    def get_can_delete(self, obj) -> bool:
        """Si quien mira puede borrarlo: lo escribió, o es su reporte.

        Es el espejo de ``CanDeleteComment``, igual que ``can_edit`` lo es del
        permiso de edición del reporte: el cliente muestra el botón según esto
        en vez de replicar la regla.
        """
        request = self.context.get("request")
        if request is None:
            return False
        return request.user.id in {obj.author_id, obj.report.author_id}


class ReportListSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.SerializerMethodField()
    # Si el municipio ya se pronunció sobre el reporte (US-024). El feed lo usa
    # para destacar la tarjeta sin traerse el hilo entero por fila.
    has_official_response = serializers.SerializerMethodField()

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
            "author",
            "like_count",
            "comment_count",
            "is_liked",
            "has_official_response",
            "created_at",
            "edited_at",
            # Cuántas veces se objetó el cierre (US-048). Un reporte *En
            # proceso* con esto en 1 volvió a gestión porque el autor objetó, y
            # el cliente lo aclara al lado del estado: no es un estado nuevo,
            # es por qué está donde está.
            "appeal_count",
            # Cuándo se archivó, para el historial personal del autor (US-031).
            # Nulo mientras el reporte no esté archivado.
            "archived_at",
            # Cuándo entró a la bandeja del área. Es el dato que la bandeja del
            # operario muestra por fila (US-045) y el criterio con el que el
            # backend la ordena. Nulo mientras el reporte no fue asignado.
            "area_assigned_at",
        ]

    def get_is_liked(self, obj) -> bool:
        """Usa la anotación del queryset si está, y si no consulta.

        ``ReportViewSet.get_queryset`` anota ``is_liked`` con un ``Exists`` para
        no disparar una query por reporte en el feed. El respaldo existe porque
        un campo declarativo se omitiría en silencio cuando falta la anotación, y
        una respuesta sin ``is_liked`` rompe el botón de like del cliente sin dar
        ninguna señal de error.
        """
        annotated = getattr(obj, "is_liked", None)
        if annotated is not None:
            return annotated
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Like.objects.filter(report=obj, user=request.user).exists()

    def get_has_official_response(self, obj) -> bool:
        """Mismo patrón que ``is_liked``: anotación si está, consulta si no."""
        annotated = getattr(obj, "official_response_count", None)
        if annotated is not None:
            return annotated > 0
        return obj.official_responses.exists()


class OperatorHistorySerializer(ReportListSerializer):
    """Un trabajo que el operario ya cerró, para su historial personal (US-046).

    Es la fila de la bandeja más la fecha del cierre **propio**. No usa
    ``Report.closed_at``: ese campo guarda el último cierre del reporte, que
    después de una apelación puede ser de otro operario del área. El dato sale
    de la anotación ``resolved_at`` que arma ``OperatorReportViewSet``, que es
    también el criterio de orden del listado.
    """

    resolved_at = serializers.DateTimeField(read_only=True)

    class Meta(ReportListSerializer.Meta):
        fields = [*ReportListSerializer.Meta.fields, "resolved_at"]


class ReportDetailSerializer(ReportListSerializer):
    comments = CommentSerializer(many=True, read_only=True)
    status_history = StatusHistorySerializer(many=True, read_only=True)
    can_edit = serializers.SerializerMethodField()
    # El hilo institucional, en orden cronológico. Va separado de los
    # comentarios a propósito: un compromiso del municipio no es un comentario
    # de un vecino, y la app los presenta como dos bloques distintos (US-024).
    official_responses = OfficialResponseSerializer(many=True, read_only=True)
    # El parte de trabajo del operario, en orden cronológico. Son varias cuando
    # hubo una apelación: el segundo cierre no pisa al primero (US-048).
    resolution_evidences = ResolutionEvidenceSerializer(many=True, read_only=True)
    resolution_appeals = ResolutionAppealSerializer(many=True, read_only=True)
    objection_deadline = serializers.SerializerMethodField()
    can_appeal = serializers.SerializerMethodField()

    class Meta(ReportListSerializer.Meta):
        fields = [
            *ReportListSerializer.Meta.fields,
            "latitude",
            "longitude",
            "address",
            "comments",
            "official_responses",
            "resolution_evidences",
            "resolution_appeals",
            "objection_deadline",
            "can_appeal",
            "status_history",
            "can_edit",
        ]

    def get_objection_deadline(self, obj) -> str | None:
        """Hasta cuándo se puede objetar el cierre (US-047, escenario 3).

        Viaja para todos y no solo para el autor: el plazo es información del
        reporte, y el feed lo muestra igual que el estado.
        """
        # Import local: ``resolution`` importa ``services``, que importa los
        # modelos; a nivel de módulo esto sería una dependencia circular.
        from urbancheck.reports.resolution import objection_deadline  # noqa: PLC0415

        if obj.status != Report.Status.RESUELTO_PENDIENTE:
            return None
        deadline = objection_deadline(obj)
        return None if deadline is None else deadline.isoformat()

    def get_can_appeal(self, obj) -> bool:
        """Si quien mira puede objetar este cierre ahora mismo (US-048).

        Lo decide el servidor y no la app: son tres condiciones —ser el autor,
        estar en el estado correcto y no haber gastado la única apelación— y
        replicarlas en el cliente era garantizar que se fueran divergiendo.
        """
        from urbancheck.reports.state_machine import (  # noqa: PLC0415
            MAX_APPEALS_PER_REPORT,
        )

        request = self.context.get("request")
        if not request or obj.author_id != request.user.id:
            return False
        return (
            obj.status == Report.Status.RESUELTO_PENDIENTE
            and obj.appeal_count < MAX_APPEALS_PER_REPORT
        )

    def get_can_edit(self, obj) -> bool:
        """True solo si quien mira es el autor y el reporte todavía es editable.

        El cliente usa esto para habilitar o deshabilitar los botones de editar y
        eliminar sin tener que replicar la regla de estados.
        """
        request = self.context.get("request")
        if not request or obj.author_id != request.user.id:
            return False
        return obj.is_editable


class ReportMapSerializer(serializers.ModelSerializer):
    """Payload mínimo para pintar marcadores y su popup (US-010)."""

    like_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            # Número de cara al usuario, correlativo dentro del municipio.
            "number",
            "photo",
            "category",
            "status",
            "latitude",
            "longitude",
            "address",
            "like_count",
            # El popup del mapa muestra el estado, así que necesita lo mismo que
            # el feed para poder aclarar que el reporte volvió por una objeción.
            "appeal_count",
        ]


class ReportCreateSerializer(serializers.ModelSerializer):
    # El GPS del teléfono manda trece decimales; se redondean en vez de
    # rechazar el reporte con un error de precisión que el vecino no entiende.
    latitude = LatitudeField(required=False, allow_null=True)
    longitude = LongitudeField(required=False, allow_null=True)

    class Meta:
        model = Report
        fields = [
            "id",
            # Número de cara al usuario, correlativo dentro del municipio.
            "number",
            "photo",
            "description",
            "category",
            "latitude",
            "longitude",
            "address",
        ]
        # ``number`` lo asigna el modelo al guardar; el cliente no lo propone.
        read_only_fields = ["id", "number"]

    def validate(self, attrs):
        # La foto no se comprueba acá: es ``required=True``, así que DRF ya la
        # rechazó a nivel de campo antes de llegar a este método.
        has_coords = attrs.get("latitude") is not None and attrs.get("longitude") is not None
        has_address = bool(attrs.get("address", "").strip())
        if not has_coords and not has_address:
            raise serializers.ValidationError(
                {"location": "Debés proporcionar coordenadas GPS o una dirección."}
            )
        return attrs


class ReportUpdateSerializer(serializers.ModelSerializer):
    """Edición del autor (US-018): solo descripción, categoría y foto.

    La ubicación no se edita: cambiarla convertiría el reporte en otro distinto y
    dejaría inconsistente el historial de estados ya registrado.
    """

    class Meta:
        model = Report
        fields = [
            "id",
            "photo",
            "description",
            "category",
            "edited_at",
        ]
        read_only_fields = ["id", "edited_at"]

    # Una descripción en blanco —vacía o de solo espacios— la rechaza DRF: el
    # ``CharField`` recorta los espacios antes de validar y ``allow_blank`` es
    # False, así que "   " llega como "" y salta el error estándar.
