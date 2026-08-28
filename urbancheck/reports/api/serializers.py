from rest_framework import serializers

from urbancheck.common.fields import LatitudeField
from urbancheck.common.fields import LongitudeField
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.users.models import User

EMPTY_DESCRIPTION_MESSAGE = "La descripción no puede quedar vacía."


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "avatar"]


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = AuthorSerializer(read_only=True)

    class Meta:
        model = ReportStatusHistory
        fields = ["status", "created_at", "changed_by"]


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
            "created_at",
            "edited_at",
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


class ReportDetailSerializer(ReportListSerializer):
    comments = CommentSerializer(many=True, read_only=True)
    status_history = StatusHistorySerializer(many=True, read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta(ReportListSerializer.Meta):
        fields = [
            *ReportListSerializer.Meta.fields,
            "latitude",
            "longitude",
            "address",
            "comments",
            "status_history",
            "can_edit",
        ]

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
        if not attrs.get("photo"):
            raise serializers.ValidationError({"photo": "La foto es obligatoria."})
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

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError(EMPTY_DESCRIPTION_MESSAGE)
        return value
