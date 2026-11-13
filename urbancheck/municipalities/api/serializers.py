from rest_framework import serializers

from urbancheck.common.fields import LatitudeField
from urbancheck.common.fields import LongitudeField
from urbancheck.municipalities.models import Municipality
from urbancheck.reports.geo import MIN_BOUNDARY_POINTS

#: Tope de vértices. Un límite municipal trazado a mano no llega ni cerca; el
#: número está para que nadie mande un GeoJSON entero por el endpoint.
MAX_BOUNDARY_POINTS = 500
LATITUDE_RANGE = (-90, 90)
LONGITUDE_RANGE = (-180, 180)

DUPLICATE_MESSAGE = "Ya existe una municipalidad registrada con esa ciudad y provincia."
CENTER_MESSAGE = "Marcá el centro del área de cobertura en el mapa."
BOUNDARY_SHAPE_MESSAGE = (
    "Trazá el límite del municipio en el mapa: hacen falta al menos tres puntos."
)
BOUNDARY_POINT_MESSAGE = (
    "El límite tiene un punto inválido: cada uno son dos números, latitud y longitud."
)
BOUNDARY_SIZE_MESSAGE = (
    f"El límite no puede tener más de {MAX_BOUNDARY_POINTS} puntos. "
    "Trazalo con menos detalle."
)


class MunicipalitySerializer(serializers.ModelSerializer[Municipality]):
    """Alta, edición y listado de municipalidades (US-017).

    El área de cobertura —el polígono del límite— es obligatoria al dar de alta:
    es lo que decide qué reportes le llegan a este municipio y cuáles no.
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
            "boundary",
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
            "boundary": {"required": True, "allow_null": False},
        }

    def create(self, validated_data):
        """Volver a dar de alta un municipio eliminado lo reactiva.

        La constraint de unicidad vale también para los dados de baja, así que
        sin esto la ciudad quedaría bloqueada para siempre. Reactivarlo además
        es lo correcto en términos de datos: recupera sus reportes y sus
        usuarios en lugar de dejarlos colgando de un municipio invisible.

        Lo que **no** hace es volver a habilitar a su personal: las cuentas que
        cayeron con la baja siguen archivadas y se reactivan de a una desde su
        pantalla. Reactivar en bloque le devolvería el acceso a gente que quizás
        ya no trabaja ahí.
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

    def validate_boundary(self, value):
        """El polígono del límite, validado punto por punto.

        Llega como JSON crudo, así que puede ser cualquier cosa. Se comprueba la
        forma completa acá y no en el modelo porque es la frontera con el
        cliente: más adentro el polígono ya se da por bien formado.
        """
        if not isinstance(value, list) or len(value) < MIN_BOUNDARY_POINTS:
            raise serializers.ValidationError(BOUNDARY_SHAPE_MESSAGE)
        if len(value) > MAX_BOUNDARY_POINTS:
            raise serializers.ValidationError(BOUNDARY_SIZE_MESSAGE)

        points = []
        for point in value:
            if not isinstance(point, (list, tuple)) or len(point) != 2:  # noqa: PLR2004
                raise serializers.ValidationError(BOUNDARY_POINT_MESSAGE)
            try:
                latitude, longitude = float(point[0]), float(point[1])
            except (TypeError, ValueError) as error:
                raise serializers.ValidationError(BOUNDARY_POINT_MESSAGE) from error
            if not (
                LATITUDE_RANGE[0] <= latitude <= LATITUDE_RANGE[1]
                and LONGITUDE_RANGE[0] <= longitude <= LONGITUDE_RANGE[1]
            ):
                raise serializers.ValidationError(BOUNDARY_POINT_MESSAGE)
            # Se normaliza a lista de floats: entra tupla, string numérico o
            # Decimal, y sale siempre lo mismo, que es lo que después se guarda.
            points.append([latitude, longitude])
        return points

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
    # El popup lo nombra por su número de municipio, no por el id de la base.
    number = serializers.IntegerField(read_only=True)
    category = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)
    address = serializers.CharField(read_only=True)
