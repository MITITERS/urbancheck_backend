"""El personal municipal solo ve reportes de la municipalidad que se le asignó.

Alcanza al validador y al agente: sus cuentas son de trabajo, no son vecinos con
un permiso extra. Quien además quiera usar UrbanCheck como ciudadano se crea una
cuenta personal.

El administrador de la plataforma queda afuera a propósito: también es cuenta de
trabajo, pero no está acotado a ningún municipio.
"""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
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


@pytest.fixture(params=["validador", "agente"])
def staff_client(request, scene) -> APIClient:
    """Las dos cuentas atadas a un municipio, con el mismo contrato."""
    factory = ValidatorFactory if request.param == "validador" else MunicipalAgentFactory
    client = APIClient()
    client.force_authenticate(
        factory.create(municipality=scene["own"], must_change_password=False),
    )
    return client


class TestStaffSeesOnlyItsOwnMunicipality:
    def test_the_feed_is_scoped(self, staff_client, scene):
        response = staff_client.get("/api/reports/")

        ids = {row["id"] for row in response.data["results"]}
        assert scene["mine"].id in ids
        assert scene["foreign"].id not in ids

    def test_the_map_is_scoped(self, staff_client, scene):
        response = staff_client.get("/api/reports/map/")

        ids = {row["id"] for row in response.data["results"]}
        assert ids == {scene["mine"].id}

    def test_a_report_of_another_municipality_does_not_exist_for_them(
        self,
        staff_client,
        scene,
    ):
        """404 y no 403: el reporte no existe para esta cuenta."""
        response = staff_client.get(f"/api/reports/{scene['foreign'].id}/")

        assert response.status_code == 404

    def test_they_cannot_comment_on_it_either(self, staff_client, scene):
        """403 y no 404, y acá el 403 no delata nada.

        Desde que el personal municipal no comenta —ver
        ``test_citizen_participation.py``—, el permiso corta antes de que la
        vista busque el reporte, así que la respuesta es la misma exista o no.
        El 404 de la jurisdicción sigue valiendo para lo que sí puede pedir.
        """
        foreign = staff_client.post(
            f"/api/reports/{scene['foreign'].id}/comments/",
            {"text": "hola"},
            format="json",
        )
        nonexistent = staff_client.post(
            "/api/reports/999999/comments/",
            {"text": "hola"},
            format="json",
        )

        assert foreign.status_code == 403
        # Lo que importa: un reporte ajeno y uno inexistente son indistinguibles.
        assert foreign.status_code == nonexistent.status_code

    def test_they_cannot_like_it_either(self, staff_client, scene):
        foreign = staff_client.post(f"/api/reports/{scene['foreign'].id}/like/")
        nonexistent = staff_client.post("/api/reports/999999/like/")

        assert foreign.status_code == 403
        assert foreign.status_code == nonexistent.status_code

    def test_reading_a_foreign_report_still_answers_404(self, staff_client, scene):
        """La ocultación por jurisdicción no cambió para lo que sí puede leer."""
        assert (
            staff_client.get(
                f"/api/reports/{scene['foreign'].id}/comments/",
            ).status_code
            == 404
        )

    def test_no_search_term_brings_a_foreign_report_back(self, staff_client, scene):
        response = staff_client.get("/api/reports/", {"search": "bache"})

        assert scene["foreign"].id not in {
            row["id"] for row in response.data["results"]
        }

    def test_even_their_own_report_elsewhere_is_hidden(self, staff_client, scene):
        """Consecuencia asumida: la cuenta de trabajo no muestra otros municipios.

        Hoy una cuenta de trabajo ya no puede crear reportes, así que esto solo
        puede darse con datos previos a esa regla. Se sigue probando porque el
        filtro es del queryset y tiene que valer igual para esos registros.
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
