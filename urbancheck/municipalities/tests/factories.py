from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from urbancheck.municipalities.models import Municipality

# Centro de Villa María. El radio por defecto es deliberadamente enorme —el
# máximo que admite el campo— para que los tests ajenos a la cobertura no tengan
# que elegir coordenadas; los que sí la ejercitan lo fijan explícitamente.
DEFAULT_CENTER = (-32.4103, -63.2400)
WIDE_RADIUS_KM = 9999


class MunicipalityFactory(DjangoModelFactory[Municipality]):
    city = factory.Sequence(lambda n: f"Ciudad {n}")
    province = factory.Sequence(lambda n: f"Provincia {n}")
    latitude = DEFAULT_CENTER[0]
    longitude = DEFAULT_CENTER[1]
    coverage_radius_km = WIDE_RADIUS_KM

    class Meta:
        model = Municipality
