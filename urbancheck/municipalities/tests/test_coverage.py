"""Área de cobertura: qué reportes le llegan a cada municipalidad.

Es la regla que evita que la capital de Córdoba vea los reportes de Villa María.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.municipalities.services import OutOfCoverageError
from urbancheck.municipalities.services import find_covering_municipality
from urbancheck.municipalities.services import resolve_municipality_for
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def active_municipality(db):
    """Anula la municipalidad de fondo del conftest.

    Ese fixture crea una con un radio enorme para que el resto de la suite no
    tenga que pensar en coordenadas — justo lo contrario de lo que este módulo
    necesita, que es controlar el mapa de cobertura entero.
    """
    return None

# Están a ~113 km una de la otra.
VILLA_MARIA = (-32.4103, -63.2400)
CORDOBA_CAPITAL = (-31.4201, -64.1888)
# Un punto en el centro de Villa María y otro en el centro de la capital.
IN_VILLA_MARIA = (-32.4110, -63.2415)
IN_CORDOBA = (-31.4180, -64.1850)


@pytest.fixture
def two_cities():
    """Dos municipios reales con radios que no se pisan."""
    villa_maria = MunicipalityFactory.create(
        city="Villa María",
        province="Córdoba",
        latitude=VILLA_MARIA[0],
        longitude=VILLA_MARIA[1],
        coverage_radius_km=15,
    )
    cordoba = MunicipalityFactory.create(
        city="Córdoba",
        province="Córdoba",
        latitude=CORDOBA_CAPITAL[0],
        longitude=CORDOBA_CAPITAL[1],
        coverage_radius_km=20,
    )
    return villa_maria, cordoba


class TestFindCovering:
    def test_a_point_resolves_to_the_city_that_covers_it(self, two_cities):
        villa_maria, cordoba = two_cities

        assert find_covering_municipality(*IN_VILLA_MARIA) == villa_maria
        assert find_covering_municipality(*IN_CORDOBA) == cordoba

    def test_a_point_between_both_belongs_to_neither(self, two_cities):
        """A mitad de camino no hay cobertura: 60 km de cada centro."""
        midpoint = (
            (VILLA_MARIA[0] + CORDOBA_CAPITAL[0]) / 2,
            (VILLA_MARIA[1] + CORDOBA_CAPITAL[1]) / 2,
        )

        assert find_covering_municipality(*midpoint) is None

    def test_overlapping_areas_resolve_to_the_nearest_center(self):
        near = MunicipalityFactory.create(
            city="Cercana",
            latitude=VILLA_MARIA[0],
            longitude=VILLA_MARIA[1],
            coverage_radius_km=50,
        )
        MunicipalityFactory.create(
            city="Lejana",
            latitude=CORDOBA_CAPITAL[0],
            longitude=CORDOBA_CAPITAL[1],
            coverage_radius_km=500,
        )

        assert find_covering_municipality(*IN_VILLA_MARIA) == near

    def test_a_deactivated_municipality_stops_receiving_reports(self, two_cities):
        villa_maria, _ = two_cities
        villa_maria.is_active = False
        villa_maria.save()

        assert find_covering_municipality(*IN_VILLA_MARIA) is None

    def test_a_municipality_without_coverage_never_matches(self):
        MunicipalityFactory.create(
            city="Sin cobertura",
            latitude=None,
            longitude=None,
            coverage_radius_km=None,
        )

        assert find_covering_municipality(*IN_VILLA_MARIA) is None


class TestResolve:
    def test_out_of_coverage_is_rejected(self, two_cities):
        """Decisión del proyecto: no se asigna a cualquiera, se rechaza."""
        with pytest.raises(OutOfCoverageError):
            resolve_municipality_for(0, 0)

    def test_without_coordinates_it_falls_back(self, two_cities, settings):
        """Sin ubicación no hay cobertura que evaluar."""
        villa_maria, _ = two_cities
        settings.ACTIVE_MUNICIPALITY_ID = villa_maria.pk

        assert resolve_municipality_for(None, None) == villa_maria


def _photo():
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, format="PNG")
    return SimpleUploadedFile("r.png", buffer.getvalue(), content_type="image/png")


class TestReportCreation:
    def test_a_report_lands_in_the_city_that_covers_it(self, two_cities):
        villa_maria, _ = two_cities
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        response = client.post(
            "/api/reports/",
            {
                "description": "Bache en el centro",
                "category": Report.Category.BACHE,
                "latitude": str(IN_VILLA_MARIA[0]),
                "longitude": str(IN_VILLA_MARIA[1]),
                "photo": _photo(),
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert Report.objects.get(pk=response.data["id"]).municipality == villa_maria

    def test_a_report_outside_every_area_is_refused(self, two_cities):
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        response = client.post(
            "/api/reports/",
            {
                "description": "Bache en medio del océano",
                "category": Report.Category.BACHE,
                "latitude": "0.0",
                "longitude": "0.0",
                "photo": _photo(),
            },
            format="multipart",
        )

        assert response.status_code == 400
        assert "location" in response.data
        assert not Report.objects.filter(description__contains="océano").exists()

    def test_neighbouring_cities_do_not_see_each_others_reports(self, two_cities):
        """El escenario que motiva la regla."""
        villa_maria, cordoba = two_cities
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        for coords in (IN_VILLA_MARIA, IN_CORDOBA):
            client.post(
                "/api/reports/",
                {
                    "description": f"Reporte en {coords}",
                    "category": Report.Category.BACHE,
                    "latitude": str(coords[0]),
                    "longitude": str(coords[1]),
                    "photo": _photo(),
                },
                format="multipart",
            )

        assert Report.objects.filter(municipality=villa_maria).count() == 1
        assert Report.objects.filter(municipality=cordoba).count() == 1
