"""El feed y el mapa del vecino se acotan al municipio donde está parado.

La app móvil manda la ubicación del ciudadano en cada carga y el servidor
responde únicamente con los reportes del municipio cuyo radio de cobertura la
contiene. Si ninguno la contiene, la pantalla viene vacía y lo dice: hay que
poder distinguir "todavía no hay reportes acá" de "estás fuera del área de toda
municipalidad adherida".
"""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import square_boundary
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

FEED_URL = "/api/reports/"
MAP_URL = "/api/reports/map/"

# Centros reales y lo bastante lejos entre sí como para que un radio chico no
# se superponga: Villa María y la capital están a unos 150 km.
VILLA_MARIA = (-32.4103, -63.2400)
CORDOBA = (-31.4201, -64.1888)
# Buenos Aires: ninguno de los dos municipios de estos tests llega hasta acá.
UNCOVERED = (-34.6037, -58.3816)

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_cities(active_municipality):
    """Dos municipios con cobertura chica, y sus reportes.

    El municipio autouse queda dado de baja a propósito: su límite es enorme
    —pensado para los tests que no miran cobertura— y cubriría cualquier punto
    del planeta, incluido el que estos tests necesitan que quede afuera.
    """
    active_municipality.is_active = False
    active_municipality.save(update_fields=["is_active"])

    villa_maria = MunicipalityFactory.create(
        city="Villa María",
        province="Córdoba",
        latitude=VILLA_MARIA[0],
        longitude=VILLA_MARIA[1],
        boundary=square_boundary(*VILLA_MARIA, 0.1),
    )
    cordoba = MunicipalityFactory.create(
        city="Córdoba",
        province="Córdoba",
        latitude=CORDOBA[0],
        longitude=CORDOBA[1],
        boundary=square_boundary(*CORDOBA, 0.1),
    )
    return {
        "villa_maria": villa_maria,
        "cordoba": cordoba,
        "villa_maria_reports": reports_near(villa_maria, VILLA_MARIA, 2),
        "cordoba_reports": reports_near(cordoba, CORDOBA, 3),
    }


def reports_near(municipality, center, count):
    """Reportes de un municipio, ubicados de verdad adentro de su radio.

    Las coordenadas van explícitas: las de la factoría son de cualquier punto
    del planeta, y desde que el acotado también mira dónde está cada reporte,
    eso ya no es un detalle irrelevante.
    """
    return [
        ReportFactory.create(
            municipality=municipality,
            # Un centésimo de grado es aproximadamente un kilómetro.
            latitude=center[0] + index * 0.01,
            longitude=center[1],
        )
        for index in range(count)
    ]


@pytest.fixture
def citizen_client():
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    return client


def feed(client, coords=None, **params):
    return _get(client, FEED_URL, coords, params)


def map_markers(client, coords=None, **params):
    return _get(client, MAP_URL, coords, params)


def _get(client, url, coords, params):
    if coords is not None:
        params |= {"latitude": coords[0], "longitude": coords[1]}
    return client.get(url, params)


class TestFeedScopedToCoverage:
    def test_only_reports_of_the_covering_municipality(
        self,
        citizen_client,
        two_cities,
    ):
        response = feed(citizen_client, VILLA_MARIA)

        assert response.status_code == 200
        returned = {report["id"] for report in response.data["results"]}
        assert returned == {r.id for r in two_cities["villa_maria_reports"]}

    def test_the_neighbouring_city_feed_is_a_different_one(
        self,
        citizen_client,
        two_cities,
    ):
        response = feed(citizen_client, CORDOBA)

        returned = {report["id"] for report in response.data["results"]}
        assert returned == {r.id for r in two_cities["cordoba_reports"]}

    def test_coverage_names_the_municipality(self, citizen_client, two_cities):
        response = feed(citizen_client, VILLA_MARIA)

        assert response.data["coverage"]["in_coverage"] is True
        assert response.data["coverage"]["municipality"]["city"] == "Villa María"

    def test_inactive_municipality_does_not_cover(self, citizen_client, two_cities):
        """Un municipio dado de baja deja de cubrir: el vecino queda afuera."""
        two_cities["villa_maria"].is_active = False
        two_cities["villa_maria"].save(update_fields=["is_active"])

        response = feed(citizen_client, VILLA_MARIA)

        assert response.data["results"] == []
        assert response.data["coverage"]["in_coverage"] is False


class TestOutOfCoverage:
    def test_feed_is_empty(self, citizen_client, two_cities):
        response = feed(citizen_client, UNCOVERED)

        assert response.status_code == 200
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_it_is_told_apart_from_a_city_with_no_reports(
        self,
        citizen_client,
        two_cities,
    ):
        """Las dos respuestas traen cero reportes y significan cosas distintas."""
        outside = feed(citizen_client, UNCOVERED)
        empty_city = feed(citizen_client, CORDOBA, category="alumbrado")

        assert outside.data["coverage"] == {"in_coverage": False, "municipality": None}
        assert empty_city.data["results"] == []
        assert empty_city.data["coverage"]["in_coverage"] is True


class TestFeedWithoutLocation:
    def test_unscoped_when_no_coordinates_are_sent(self, citizen_client, two_cities):
        """Sin ubicación el feed no se acota: un cliente viejo sigue andando."""
        response = feed(citizen_client)

        assert response.data["count"] == 5
        assert "coverage" not in response.data

    def test_unreadable_coordinates_are_ignored(self, citizen_client, two_cities):
        """Un parámetro roto no rompe el feed ni devuelve 400."""
        response = citizen_client.get(FEED_URL, {"latitude": "acá", "longitude": ""})

        assert response.status_code == 200
        assert response.data["count"] == 5


class TestOwnReportsAreNotScoped:
    def test_mine_survives_being_out_of_coverage(self, citizen_client, two_cities):
        """"Mis reportes" son del autor, no del lugar donde abre la app."""
        author = UserFactory.create()
        mine = ReportFactory.create(
            author=author,
            municipality=two_cities["villa_maria"],
        )
        client = APIClient()
        client.force_authenticate(author)

        response = feed(client, UNCOVERED, mine="true")

        assert [report["id"] for report in response.data["results"]] == [mine.id]
        assert "coverage" not in response.data


class TestMapIsScopedToo:
    """El mapa se acota igual que el feed: es la misma vista, en otro formato."""

    def test_only_markers_of_the_covering_municipality(
        self,
        citizen_client,
        two_cities,
    ):
        response = map_markers(citizen_client, VILLA_MARIA)

        assert response.status_code == 200
        returned = {marker["id"] for marker in response.data["results"]}
        assert returned == {r.id for r in two_cities["villa_maria_reports"]}

    def test_out_of_coverage_map_is_empty_and_says_so(self, citizen_client, two_cities):
        response = map_markers(citizen_client, UNCOVERED)

        assert response.data["results"] == []
        assert response.data["coverage"] == {"in_coverage": False, "municipality": None}

    def test_unscoped_without_location(self, citizen_client, two_cities):
        response = map_markers(citizen_client)

        assert len(response.data["results"]) == 5
        assert "coverage" not in response.data


class TestReportsOutsideTheirOwnMunicipality:
    """Pertenecer al municipio no alcanza: el reporte tiene que estar adentro.

    Es el caso de los reportes cargados antes de que existiera la cobertura, o
    de los que cayeron en el respaldo de ``ACTIVE_MUNICIPALITY_ID`` por no tener
    coordenadas: apuntan al municipio, pero están a decenas de kilómetros.
    """

    def test_a_far_away_report_is_not_shown(self, citizen_client, two_cities):
        far_away = ReportFactory.create(
            municipality=two_cities["villa_maria"],
            latitude=CORDOBA[0],
            longitude=CORDOBA[1],
        )

        response = feed(citizen_client, VILLA_MARIA)

        assert far_away.id not in {report["id"] for report in response.data["results"]}

    def test_neither_on_the_map(self, citizen_client, two_cities):
        far_away = ReportFactory.create(
            municipality=two_cities["villa_maria"],
            latitude=CORDOBA[0],
            longitude=CORDOBA[1],
        )

        response = map_markers(citizen_client, VILLA_MARIA)

        assert far_away.id not in {marker["id"] for marker in response.data["results"]}

    def test_a_report_without_coordinates_stays(self, citizen_client, two_cities):
        """Sin coordenadas no hay dónde ubicarlo: vale el municipio que tiene."""
        located_nowhere = ReportFactory.create(
            municipality=two_cities["villa_maria"],
            latitude=None,
            longitude=None,
        )

        response = feed(citizen_client, VILLA_MARIA)

        returned = {report["id"] for report in response.data["results"]}
        assert located_nowhere.id in returned
