from rest_framework import serializers

from urbancheck.common.fields import LatitudeField
from urbancheck.common.fields import LongitudeField
from urbancheck.municipalities.models import Municipality

DUPLICATE_MESSAGE = "Ya existe una municipalidad registrada con esa ciudad y provincia."
RADIUS_MESSAGE = "El radio de cobertura tiene que ser mayor a cero."
CENTER_MESSAGE = "Marcá el centro del área de cobertura en el mapa."


class MunicipalitySerializer(serializers.ModelSerializer[Municipality]):
    """Alta, edición y listado de municipalidades (US-017).

    El área de cobertura —centro y radio— es obligatoria al dar de alta: es lo
    que decide qué reportes le llegan a este municipio y cuáles no.
    """

    report_count = serializers.IntegerField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)
    # El centroide oficial de Georef trae trece decimales.
    latitude = LatitudeField()
    longitude = LongitudeField()

    class Meta:
        model = Municipality
        fields = [
            "id",
            "city",
            "province",
            "latitude",
            "longitude",
            "coverage_radius_km",
            "is_active",
            "report_count",
            "user_count",
            "created_at",
        ]
        read_only_fields = ["id", "is_active", "created_at"]
        # La constraint del modelo genera un UniqueTogetherValidator que responde
        # en ``non_field_errors``. Lo desactivamos: la comprobación de abajo
        # ignora mayúsculas y espacios y devuelve el error en el campo, que es
        # donde el panel lo muestra.
        validators = []
        extra_kwargs = {
            "coverage_radius_km": {"required": True, "allow_null": False},
        }

    def create(self, validated_data):
        """Volver a dar de alta un municipio eliminado lo reactiva.

        La constraint de unicidad vale también para los dados de baja, así que
        sin esto la ciudad quedaría bloqueada para siempre. Reactivarlo además
        es lo correcto en términos de datos: recupera sus reportes y usuarios en
        lugar de dejarlos colgando de un municipio invisible.
        """
        revived = Municipality.objects.filter(
            city__iexact=validated_data["city"],
            province__iexact=validated_data["province"],
            is_active=False,
        ).first()
        if revived is None:
            return super().create(validated_data)

        for field, value in validated_data.items():
            setattr(revived, field, value)
        revived.is_active = True
        revived.save()
        return revived

    def validate_coverage_radius_km(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError(RADIUS_MESSAGE)
        return value

    def validate(self, attrs):
        city = attrs.get("city", getattr(self.instance, "city", "")).strip()
        province = attrs.get("province", getattr(self.instance, "province", "")).strip()

        # Solo las vigentes: una dada de baja no bloquea el nombre, se revive
        # al volver a darla de alta (ver ``create``).
        duplicates = Municipality.objects.active().filter(
            city__iexact=city,
            province__iexact=province,
        )
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"city": DUPLICATE_MESSAGE})

        attrs["city"] = city
        attrs["province"] = province
        return attrs


class MunicipalityReportMarkerSerializer(serializers.Serializer):
    """Payload mínimo del mapa: un marcador no necesita más que esto."""

    id = serializers.IntegerField(read_only=True)
    category = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    address = serializers.CharField(read_only=True)
