"""Coordenadas: se redondean, no se rechazan."""

from decimal import Decimal

import pytest
from rest_framework import serializers

from urbancheck.common.fields import LatitudeField
from urbancheck.common.fields import LongitudeField

# Lo que devuelven de verdad el GPS de un teléfono y los centroides de Georef.
GPS_LATITUDE = "-32.6303142822017"
GPS_LONGITUDE = "-62.6887933841481"


class TestRounding:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (GPS_LATITUDE, "-32.630314"),
            ("-32.6303148", "-32.630315"),
            ("-32.63", "-32.630000"),
            ("0", "0.000000"),
            (-32.6303142822017, "-32.630314"),
        ],
    )
    def test_extra_precision_is_rounded(self, raw, expected):
        assert LatitudeField().to_internal_value(raw) == Decimal(expected)

    def test_longitude_too(self):
        assert LongitudeField().to_internal_value(GPS_LONGITUDE) == Decimal(
            "-62.688793",
        )


class TestValidation:
    @pytest.mark.parametrize("raw", ["91", "-90.5", "1000"])
    def test_a_latitude_off_the_planet_is_rejected(self, raw):
        """Más precisión es un dato de sobra; fuera de rango es un error."""
        with pytest.raises(serializers.ValidationError):
            LatitudeField().to_internal_value(raw)

    @pytest.mark.parametrize("raw", ["181", "-180.001"])
    def test_a_longitude_off_the_planet_is_rejected(self, raw):
        with pytest.raises(serializers.ValidationError):
            LongitudeField().to_internal_value(raw)

    @pytest.mark.parametrize("raw", ["", "hola", "NaN", "Infinity", None])
    def test_garbage_is_rejected(self, raw):
        with pytest.raises(serializers.ValidationError):
            LatitudeField().to_internal_value(raw)

    @pytest.mark.parametrize("raw", ["-90", "90", "0"])
    def test_the_limits_themselves_are_valid(self, raw):
        assert LatitudeField().to_internal_value(raw) == Decimal(raw).quantize(
            Decimal("0.000001"),
        )
