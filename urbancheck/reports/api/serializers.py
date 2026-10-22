from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from urbancheck.common.fields import LatitudeField
from urbancheck.common.fields import LongitudeField
from urbancheck.common.fields import PendingPhotoField
from urbancheck.reports.models import COMPLAINT_COMMENT_MAX_LENGTH
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.privacy import deadline_for
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
        fields = [
            "id",
            "photo",
            # Cuándo se retiró la foto por protección de datos (US-043,
            # escenario 11). La app muestra "imagen retirada" en su lugar.
            "photo_removed_at",
            # La foto del cierre pasa por el mismo circuito que la del reporte
            # (US-042, escenario 8): hasta que termina, el hilo la muestra
            # como en procesamiento en vez de como ausente.
            "photo_status",
            "description",
            "created_at",
            "operational_area",
        ]
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
        # ``photo_removed_at``: la foto se retiró por protección de datos
        # (US-043) y la app muestra "imagen retirada" en su lugar.
        fields = [
            "id",
            "photo",
            "photo_status",
            "photo_removed_at",
            "reason",
            "created_at",
        ]
        read_only_fields = fields


class ModerationAppealStateSerializer(serializers.Serializer):
    """La apelación del autor contra un descarte, tal como la ve él (US-049)."""

    status = serializers.CharField()
    reason = serializers.CharField()
    created_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField(allow_null=True)
    resolution_reason = serializers.CharField(allow_blank=True)


class PublicModerationSerializer(serializers.Serializer):
    """El descarte por moderación de un reporte, de cara al público (US-049).

    Es la **única** información de la moderación que ve el ciudadano: qué se
    decidió, por qué y cuándo. No viajan la identidad de los denunciantes, la
    del agente ni la cantidad de denuncias. La apelación y la posibilidad de
    apelar solo le llegan al autor.
    """

    reason = serializers.CharField()
    decided_at = serializers.DateTimeField()
    can_appeal = serializers.BooleanField()
    appeal = ModerationAppealStateSerializer(allow_null=True)


def moderation_payload(report, request) -> dict | None:
    """El descarte vigente de ``report`` para quien hace ``request``."""
    decision = report.active_discard()
    if decision is None:
        return None
    is_author = bool(request) and report.author_id == request.user.id
    appeal = decision.appeals.first() if is_author else None
    return {
        "reason": decision.reason,
        "decided_at": decision.created_at,
        "can_appeal": is_author and not decision.appeals.exists(),
        "appeal": (
            {
                "status": appeal.status,
                "reason": appeal.reason,
                "created_at": appeal.created_at,
                "resolved_at": appeal.resolved_at,
                "resolution_reason": appeal.resolution_reason,
            }
            if appeal
            else None
        ),
    }


class ModerationNoticeSerializer(serializers.ModelSerializer):
    """Un reporte descartado por moderación, abierto por un tercero (US-049).

    El reporte ya no está publicado —salió del feed y del mapa por su estado—,
    pero el motivo del descarte es público: es el contrapeso de que el municipio
    pueda sacar reclamos de la vista. Así que se muestra el aviso y **nada
    más**: sin foto, sin descripción, sin autor, sin comentarios.
    """

    moderation = serializers.SerializerMethodField()
    is_moderation_notice = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "number",
            "category",
            "status",
            "created_at",
            "moderation",
            "is_moderation_notice",
        ]
        read_only_fields = fields

    @extend_schema_field(PublicModerationSerializer(allow_null=True))
    def get_moderation(self, obj) -> dict | None:
        return moderation_payload(obj, self.context.get("request"))

    def get_is_moderation_notice(self, obj) -> bool:
        return True


class ModerationAppealCreateSerializer(serializers.Serializer):
    """La apelación del autor contra un descarte (US-049): solo el motivo."""

    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class ResolutionCreateSerializer(serializers.Serializer):
    """El parte de trabajo que sube el operario al cerrar (US-046).

    Los tres campos son obligatorios y por motivos distintos: sin foto no hay
    evidencia de que el trabajo se hizo, sin descripción no se sabe qué se hizo,
    y sin coordenadas no se puede verificar que quien cierra estuvo en el lugar.

    Es un ``Serializer`` y no un ``ModelSerializer`` porque lo que recibe no es
    la evidencia entera: el operario, el área y el reporte los pone el servidor.
    """

    photo = PendingPhotoField()
    description = serializers.CharField(allow_blank=False, trim_whitespace=True)
    latitude = LatitudeField()
    longitude = LongitudeField()


class ResolutionAppealCreateSerializer(serializers.Serializer):
    """La objeción del autor al cierre (US-048).

    Motivo y foto son obligatorios: una apelación sin evidencia no se distingue
    de una objeción caprichosa y no reabre trabajo municipal.
    """

    photo = PendingPhotoField()
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
    # Si el reporte está retenido por una solicitud de protección de datos
    # (US-043). Solo el autor lo ve en ``True``: para cualquier otro, un reporte
    # retenido directamente no aparece.
    under_privacy_review = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            # Número de cara al usuario, correlativo dentro del municipio.
            "number",
            "photo",
            # Cuándo se retiró la foto por protección de datos (US-043). Nulo
            # si la tiene: ``photo`` nulo con esto cargado es "imagen retirada".
            "photo_removed_at",
            # En qué anda el difuminado de la imagen (US-042). Solo puede
            # verse distinto de "procesada" en el listado propio del autor y en
            # el panel: para cualquier otro, un reporte sin procesar no aparece.
            "photo_status",
            "under_privacy_review",
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

    def get_under_privacy_review(self, obj) -> bool:
        return obj.is_on_privacy_hold


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
    # Solo las objeciones de cierre: las de moderación comparten modelo (US-049)
    # pero van en ``moderation``.
    resolution_appeals = ResolutionAppealSerializer(
        source="closure_appeals",
        many=True,
        read_only=True,
    )
    objection_deadline = serializers.SerializerMethodField()
    can_appeal = serializers.SerializerMethodField()
    # El descarte por moderación vigente (US-049). Su motivo es público.
    moderation = serializers.SerializerMethodField()
    # El enlace para compartirlo (US-030). Solo si el reporte es público: un
    # enlace a algo que nadie más puede ver no se ofrece.
    share_url = serializers.SerializerMethodField()

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
            "moderation",
            "share_url",
            "status_history",
            "can_edit",
        ]

    def get_share_url(self, obj) -> str | None:
        # Import local: ``public_views`` importa este módulo.
        from .public_views import share_url_for  # noqa: PLC0415

        if not Report.objects.publicly_visible().filter(pk=obj.pk).exists():
            return None
        return share_url_for(obj)

    @extend_schema_field(PublicModerationSerializer(allow_null=True))
    def get_moderation(self, obj) -> dict | None:
        return moderation_payload(obj, self.context.get("request"))

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
    # Entra a la cola de difuminado y se guarda en el storage privado; `photo`
    # queda vacía hasta que la tarea termina (US-042). `write_only` no es
    # decorativo: devolver el campo intentaría resolver `photo_pending.url`, que
    # por diseño no existe.
    photo = PendingPhotoField(source="photo_pending", write_only=True)
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
            # La respuesta del alta ya sale en "pendiente": el cliente lo usa
            # para no decirle al ciudadano que su reporte está publicado
            # cuando todavía no lo está.
            "photo_status",
            "description",
            "category",
            "latitude",
            "longitude",
            "address",
        ]
        # ``number`` lo asigna el modelo al guardar; el cliente no lo propone.
        read_only_fields = ["id", "number", "photo_status"]

    def validate(self, attrs):
        # La foto no se comprueba acá: es ``required=True``, así que DRF ya la
        # rechazó a nivel de campo antes de llegar a este método.
        return validate_report_location(attrs)


def validate_report_location(attrs):
    """Un reporte tiene que poder ubicarse: con coordenadas o con dirección."""
    has_coords = (
        attrs.get("latitude") is not None and attrs.get("longitude") is not None
    )
    has_address = bool(attrs.get("address", "").strip())
    if not has_coords and not has_address:
        raise serializers.ValidationError(
            {"location": "Debés proporcionar coordenadas GPS o una dirección."},
        )
    return attrs


class ReportLocationSerializer(serializers.ModelSerializer):
    """Lo que hace falta para saber si un reporte ya existe (US-032), sin la foto.

    Se valida **antes** que ``ReportCreateSerializer`` porque la foto se
    difumina dentro de su ``is_valid()``: si el reporte termina rechazado por
    duplicado, la imagen no tiene que haber entrado al circuito de
    anonimización (escenario 7).
    """

    latitude = LatitudeField(required=False, allow_null=True)
    longitude = LongitudeField(required=False, allow_null=True)

    class Meta:
        model = Report
        fields = ["category", "latitude", "longitude", "address"]

    def validate(self, attrs):
        return validate_report_location(attrs)


class ExistingReportSerializer(ReportListSerializer):
    """El reclamo que ya describe el problema, en la respuesta ``409`` (US-032).

    Trae lo necesario para que la app ofrezca sumarse sin otra llamada:
    ``is_liked`` para no ofrecerlo a quien ya apoya, ``is_author`` para no
    ofrecérselo a quien lo creó, y a qué distancia está del punto reportado.
    """

    distance_meters = serializers.SerializerMethodField()
    is_author = serializers.SerializerMethodField()

    class Meta(ReportListSerializer.Meta):
        fields = [
            *ReportListSerializer.Meta.fields,
            "address",
            "distance_meters",
            "is_author",
        ]

    def get_distance_meters(self, obj) -> int | None:
        distance = getattr(obj, "distance_meters", None)
        return None if distance is None else round(distance)

    def get_is_author(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.author_id == request.user.id)


class ReportUpdateSerializer(serializers.ModelSerializer):
    """Edición del autor (US-018): solo descripción, categoría y foto.

    La ubicación no se edita: cambiarla convertiría el reporte en otro distinto y
    dejaría inconsistente el historial de estados ya registrado.
    """

    # La foto de reemplazo pasa por el mismo circuito que la original, con una
    # consecuencia visible: el reporte vuelve a ocultarse hasta que se procese
    # (US-042). Publicar la nueva sin difuminar sería la vía degradada que la
    # historia descarta.
    photo = PendingPhotoField(source="photo_pending", write_only=True)

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


COMPLAINT_REASON_REQUIRED_MESSAGE = "El motivo es obligatorio."


class PrivacyRequestCreateSerializer(serializers.Serializer):
    """La solicitud de revisión por dato personal visible (US-043).

    Sin ``evidence`` ni ``appeal`` se denuncia la foto del reporte; con
    ``evidence``, la de ese parte de trabajo del operario, y con ``appeal``, la
    de esa objeción del autor. El reporte lo fija la URL.
    """

    evidence = serializers.IntegerField(required=False, allow_null=True)
    appeal = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs.get("evidence") is not None and attrs.get("appeal") is not None:
            msg = "Indicá una sola imagen: la de un cierre o la de una objeción."
            raise serializers.ValidationError(msg)
        return attrs


class ComplaintCreateSerializer(serializers.Serializer):
    """Denunciar un reporte (US-021): motivo obligatorio, comentario opcional.

    Los motivos válidos son los del catálogo del modelo; el reporte lo fija la
    URL y el denunciante, la sesión.
    """

    reason = serializers.ChoiceField(
        choices=ReportComplaint.Reason.choices,
        # Un motivo vacío tiene que decir "es obligatorio", no "no existe":
        # se deja pasar acá y lo rechaza ``validate_reason``.
        allow_blank=True,
        error_messages={
            "required": COMPLAINT_REASON_REQUIRED_MESSAGE,
            "null": COMPLAINT_REASON_REQUIRED_MESSAGE,
            "invalid_choice": "El motivo elegido no existe.",
        },
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=COMPLAINT_COMMENT_MAX_LENGTH,
    )

    def validate_reason(self, value):
        if not value:
            raise serializers.ValidationError(COMPLAINT_REASON_REQUIRED_MESSAGE)
        return value


class ComplaintReceiptSerializer(serializers.ModelSerializer):
    """El acuse de una denuncia (US-021, escenario 1).

    ``recipient`` dice a quién quedó dirigida. No lleva al denunciante: quien
    la presentó ya sabe quién es, y este serializer no se usa para nadie más.
    """

    received_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ReportComplaint
        fields = ["id", "report", "reason", "recipient", "comment", "received_at"]
        read_only_fields = fields


class PrivacyRequestReceiptSerializer(serializers.ModelSerializer):
    """El acuse que recibe quien denuncia (US-043, escenario 1).

    Lleva la fecha de recepción y la fecha límite para que la app pueda decirle
    al vecino hasta cuándo, no solo "en 24 horas".
    """

    received_at = serializers.DateTimeField(source="created_at", read_only=True)
    deadline = serializers.SerializerMethodField()
    evidence = serializers.IntegerField(source="resolution_evidence_id", read_only=True)
    appeal = serializers.IntegerField(source="resolution_appeal_id", read_only=True)

    class Meta:
        model = ReportComplaint
        fields = [
            "id",
            "report",
            "evidence",
            "appeal",
            "reason",
            "status",
            "received_at",
            "deadline",
        ]
        read_only_fields = fields

    def get_deadline(self, obj) -> str:
        return deadline_for(obj).isoformat()
