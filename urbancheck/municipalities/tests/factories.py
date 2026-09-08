from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from urbancheck.municipalities.models import Municipality

# Centro de Villa María. El límite por defecto es deliberadamente enorme —medio
# planeta— para que los tests ajenos a la cobertura no tengan que elegir
# coordenadas; los que sí la ejercitan lo fijan explícitamente.
DEFAULT_CENTER = (-32.4103, -63.2400)


def square_boundary(latitude, longitude, half_side_degrees):
    """Cuadrado centrado en el punto, en grados. Atajo para los tests.

    Un cuadrado y no un círculo aproximado: para comprobar que un punto entra o
    no en un área, la forma exacta da lo mismo y esta se lee de un vistazo.
    """
    return [
        [latitude - half_side_degrees, longitude - half_side_degrees],
        [latitude - half_side_degrees, longitude + half_side_degrees],
        [latitude + half_side_degrees, longitude + half_side_degrees],
        [latitude + half_side_degrees, longitude - half_side_degrees],
    ]


WIDE_BOUNDARY = square_boundary(*DEFAULT_CENTER, 45)


class MunicipalityFactory(DjangoModelFactory[Municipality]):
    city = factory.Sequence(lambda n: f"Ciudad {n}")
    province = factory.Sequence(lambda n: f"Provincia {n}")
    latitude = DEFAULT_CENTER[0]
    longitude = DEFAULT_CENTER[1]
    boundary = factory.LazyFunction(lambda: [list(point) for point in WIDE_BOUNDARY])

    class Meta:
        model = Municipality
