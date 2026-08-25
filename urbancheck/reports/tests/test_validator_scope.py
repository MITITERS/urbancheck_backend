"""El validador solo ve reportes de la municipalidad que se le asignó.

Su cuenta es de trabajo: no es un vecino con un permiso extra. Quien además
quiera usar UrbanCheck como ciudadano se crea una cuenta personal.
"""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_cities():
    return MunicipalityFactory.create(city="Villa María"), MunicipalityFactory.create(
        city="Villa Nueva",
    )


@pytest.fixture
def scene(two_cities):
    """Un reporte visible en cada municipio."""
    own, other = two_cities
    return {
        "own": own,
        "other": other,
        "mine": ReportFactory.create(municipality=own, status=Report.Status.REPORTADO),
        "foreign": ReportFactory.create(
            municipality=other,
            status=Report.Status.REPORTADO,
        ),
    }


@pytest.fixture
def validator_client(scene) -> APIClient:
    client = APIClient()
    client.force_authenticate(
        ValidatorFactory.create(municipality=scene["own"], must_change_password=False),
    )
    return client


class TestValidatorSeesOnlyItsOwnMunicipality:
    def test_the_feed_is_scoped(self, validator_client, scene):
        response = validator_client.get("/api/reports/")

        ids = {row["id"] for row in response.data["results"]}
        assert scene["mine"].id in ids
        assert scene["foreign"].id not in ids

    def test_the_map_is_scoped(self, validator_client, scene):
        response = validator_client.get("/api/reports/map/")

        ids = {row["id"] for row in response.data["results"]}
        assert ids == {scene["mine"].id}

    def test_a_report_of_another_municipality_does_not_exist_for_them(
        self,
        validator_client,
        scene,
    ):
        """404 y no 403: el reporte no existe para esta cuenta."""
        response = validator_client.get(f"/api/reports/{scene['foreign'].id}/")

        assert response.status_code == 404

    def test_they_cannot_comment_on_it_either(self, validator_client, scene):
        response = validator_client.post(
            f"/api/reports/{scene['foreign'].id}/comments/",
            {"text": "hola"},
            format="json",
        )

        assert response.status_code == 404

    def test_they_cannot_like_it_either(self, validator_client, scene):
        response = validator_client.post(f"/api/reports/{scene['foreign'].id}/like/")

        assert response.status_code == 404

    def test_no_search_term_brings_a_foreign_report_back(self, validator_client, scene):
        response = validator_client.get("/api/reports/", {"search": "bache"})

        assert scene["foreign"].id not in {
            row["id"] for row in response.data["results"]
        }

    def test_even_their_own_report_elsewhere_is_hidden(self, validator_client, scene):
        """Consecuencia asumida: la cuenta de trabajo no muestra otros municipios.

        Un validador que reporta algo fuera de su jurisdicción lo hace desde su
        cuenta personal.
        """
        validator = ValidatorFactory.create(
            municipality=scene["own"],
            must_change_password=False,
        )
        client = APIClient()
        client.force_authenticate(validator)
        own_report_elsewhere = ReportFactory.create(
            municipality=scene["other"],
            author=validator,
            status=Report.Status.REPORTADO,
        )

        response = client.get("/api/reports/", {"mine": "true"})

        assert own_report_elsewhere.id not in {
            row["id"] for row in response.data["results"]
        }


class TestCitizensAreUnaffected:
    def test_a_citizen_still_sees_the_whole_community(self, scene):
        """El feed sigue siendo comunitario para el vecino común."""
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        response = client.get("/api/reports/")

        ids = {row["id"] for row in response.data["results"]}
        assert {scene["mine"].id, scene["foreign"].id} <= ids

    def test_a_citizen_can_open_any_report(self, scene):
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        response = client.get(f"/api/reports/{scene['foreign'].id}/")

        assert response.status_code == 200
