"""Serializers de la gestión de áreas operativas (US-039)."""

from rest_framework import serializers

from urbancheck.municipalities.models import AREA_NAME_TAKEN_MESSAGE
from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.models import OperationalArea


class OperationalAreaSerializer(serializers.ModelSerializer[OperationalArea]):
    """Alta, edición y listado de un área operativa.

    La municipalidad **no** es un campo del cliente: se resuelve en el servidor
    desde el usuario autenticado (US-034). El admin de la plataforma, que no
    tiene jurisdicción propia, la elige con ``municipality_id`` — mismo criterio
    que el alta de validadores de US-035.

    ``is_active`` tampoco se edita acá: la baja y el alta lógicas van por sus
    propias acciones, para que una edición de contacto no pueda desactivar un
    área por accidente.
    """

    report_count = serializers.IntegerField(read_only=True)
    operator_count = serializers.IntegerField(read_only=True)
    municipality_id = serializers.PrimaryKeyRelatedField(
        queryset=Municipality.objects.active(),
        source="municipality",
        write_only=True,
        required=False,
    )
    municipality = serializers.SerializerMethodField()

    class Meta:
        model = OperationalArea
        fields = [
            "id",
            "name",
            "contact_email",
            "contact_phone",
            "is_active",
            "report_count",
            "operator_count",
            "municipality",
            "municipality_id",
            "created_at",
        ]
        read_only_fields = ["id", "is_active", "created_at"]
        # La constraint compuesta del modelo respondería en ``non_field_errors``
        # y con el texto de la base. La comprobación de abajo devuelve el error
        # sobre ``name``, que es donde el panel lo muestra.
        validators = []

    def get_municipality(self, obj) -> dict | None:
        """Jurisdicción del área, resumida.

        Viaja siempre, aunque para el agente sea constante: es lo que el admin
        necesita para distinguir filas de municipios distintos, y una sola forma
        de la respuesta es más fácil de sostener que dos.
        """
        if obj.municipality_id is None:
            return None
        return {
            "id": obj.municipality_id,
            "city": obj.municipality.city,
            "province": obj.municipality.province,
            "is_active": obj.municipality.is_active,
        }

    def _municipality_for(self, attrs) -> Municipality:
        """De dónde sale la jurisdicción del área.

        El agente tiene la suya y no puede elegir otra: si el body trae una, se
        ignora. El admin no está acotado a ninguna, así que la elige. En una
        edición se conserva la que ya tenía — la jurisdicción no se muda.
        """
        if self.instance is not None:
            return self.instance.municipality
        user = self.context["request"].user
        if user.municipality_id:
            return user.municipality
        return attrs.get("municipality")

    def validate(self, attrs):
        municipality = self._municipality_for(attrs)
        if municipality is None:
            raise serializers.ValidationError(
                {"municipality_id": "Elegí una municipalidad."},
            )
        attrs["municipality"] = municipality

        name = attrs.get("name", getattr(self.instance, "name", "")).strip()
        # El mismo nombre sí puede existir en otra municipalidad: la unicidad es
        # compuesta, igual que la constraint del modelo.
        duplicates = OperationalArea.objects.filter(
            municipality=municipality,
            name__iexact=name,
        )
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"name": AREA_NAME_TAKEN_MESSAGE})

        attrs["name"] = name
        return attrs
