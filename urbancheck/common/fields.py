"""Campos de serializer compartidos entre apps."""

from decimal import ROUND_HALF_UP
from decimal import Decimal
from decimal import InvalidOperation

from rest_framework import serializers

#: Precisión con la que se guardan las coordenadas: ~11 cm. Más que suficiente
#: para ubicar un bache, y lo que admiten los campos del modelo.
COORDINATE_DECIMAL_PLACES = 6
COORDINATE_MAX_DIGITS = 9
_QUANTUM = Decimal(1).scaleb(-COORDINATE_DECIMAL_PLACES)

LATITUDE_RANGE = (Decimal(-90), Decimal(90))
LONGITUDE_RANGE = (Decimal(-180), Decimal(180))


class CoordinateField(serializers.DecimalField):
    """Latitud o longitud, redondeada en lugar de rechazada.

    El GPS de un teléfono y los centroides de Georef vienen con trece decimales;
    el modelo guarda seis. Un ``DecimalField`` común rechaza esa entrada con
    «no puede haber más de 9 dígitos en total», que para el usuario es un error
    incomprensible sobre un dato que él no escribió. Acá se redondea: más
    precisión de la que guardamos no es un dato inválido, es un dato de sobra.

    Lo que sí se rechaza es una coordenada fuera del rango terrestre, que es un
    error de verdad.
    """

    def __init__(self, *, limits: tuple[Decimal, Decimal], **kwargs):
        kwargs.setdefault("max_digits", COORDINATE_MAX_DIGITS)
        kwargs.setdefault("decimal_places", COORDINATE_DECIMAL_PLACES)
        self.limits = limits
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            value = Decimal(str(data).strip())
        except (InvalidOperation, ValueError, TypeError):
            self.fail("invalid")

        if not value.is_finite():
            self.fail("invalid")

        low, high = self.limits
        if not low <= value <= high:
            message = f"La coordenada tiene que estar entre {low} y {high}."
            raise serializers.ValidationError(message)

        rounded = value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
        return super().to_internal_value(str(rounded))


class LatitudeField(CoordinateField):
    def __init__(self, **kwargs):
        super().__init__(limits=LATITUDE_RANGE, **kwargs)


class LongitudeField(CoordinateField):
    def __init__(self, **kwargs):
        super().__init__(limits=LONGITUDE_RANGE, **kwargs)
