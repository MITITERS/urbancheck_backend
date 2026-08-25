"""US-034 — restricción por jurisdicción.

El test de fuga es el corazón de esta historia: dos municipalidades pobladas y
la verificación, endpoint por endpoint, de que un agente no ve ni un registro
de la otra.
"""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

PANEL_LIST_URL = "/api/panel/reports/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_municipalities():
    """Dos municipios poblados: el propio y el ajeno."""
    own = MunicipalityFactory.create(city="Villa María", province="Córdoba")
    other = MunicipalityFactory.create(city="Villa Nueva", province="Córdoba")
    own_reports = ReportFactory.create_batch(3, municipality=own)
    other_reports = ReportFactory.create_batch(4, municipality=other)
    return {
        "own": own,
        "other": other,
        "own_reports": own_reports,
        "other_reports": other_reports,
    }


@pytest.fixture
def agent_client(two_municipalities):
    client = APIClient()
    client.force_authenticate(
        MunicipalAgentFactory.create(municipality=two_municipalities["own"]),
    )
    return client


class TestPanelListDoesNotLeak:
    def test_only_own_municipality_reports_are_listed(
        self,
        agent_client,
        two_municipalities,
    ):
        response = agent_client.get(PANEL_LIST_URL)

        assert response.status_code == 200
        returned = {row["id"] for row in response.data["results"]}
        assert returned == {r.id for r in two_municipalities["own_reports"]}

    def test_no_report_of_the_other_municipality_appears(
        self,
        agent_client,
        two_municipalities,
    ):
        response = agent_client.get(PANEL_LIST_URL)

        returned = {row["id"] for row in response.data["results"]}
        for report in two_municipalities["other_reports"]:
            assert report.id not in returned

    @pytest.mark.parametrize(
        "params",
        [
            {"municipality": "2"},
            {"municipality_id": "2"},
            {"municipality__id": "2"},
        ],
    )
    def test_a_municipality_parameter_from_the_client_is_ignored(
        self,
        agent_client,
        two_municipalities,
        params,
    ):
        """La jurisdicción se deriva del usuario, nunca del request."""
        params = {**params, "municipality": str(two_municipalities["other"].pk)}

        response = agent_client.get(PANEL_LIST_URL, params)

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {r.id for r in two_municipalities["own_reports"]}


class TestDirectAccessIsDenied:
    def test_detail_of_another_municipality_returns_404_not_403(
        self,
        agent_client,
        two_municipalities,
    ):
        """404 y no 403: un 403 confirmaría que el reporte existe."""
        foreign = two_municipalities["other_reports"][0]

        response = agent_client.get(f"{PANEL_LIST_URL}{foreign.id}/")

        assert response.status_code == 404

    def test_detail_of_own_municipality_is_reachable(
        self,
        agent_client,
        two_municipalities,
    ):
        own = two_municipalities["own_reports"][0]

        response = agent_client.get(f"{PANEL_LIST_URL}{own.id}/")

        assert response.status_code == 200
        assert response.data["id"] == own.id


class TestPanelPermissions:
    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, PlatformAdminFactory],
        ids=["citizen", "validator", "platform_admin"],
    )
    def test_only_municipal_agents_reach_the_panel(self, factory):
        client = APIClient()
        client.force_authenticate(factory.create())

        assert client.get(PANEL_LIST_URL).status_code == 403


class TestForUserQueryset:
    def test_filters_by_the_municipality_of_the_user(self, two_municipalities):
        agent = MunicipalAgentFactory.create(municipality=two_municipalities["own"])

        result = Report.objects.for_user(agent)

        assert set(result) == set(two_municipalities["own_reports"])

    def test_validator_is_scoped_the_same_way(self, two_municipalities):
        """Escenario 7: el validador opera solo sobre su municipalidad."""
        validator = ValidatorFactory.create(municipality=two_municipalities["other"])

        result = Report.objects.for_user(validator)

        assert set(result) == set(two_municipalities["other_reports"])

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, PlatformAdminFactory],
        ids=["citizen", "platform_admin"],
    )
    def test_a_user_without_municipality_gets_nothing(self, factory, two_municipalities):
        """Default seguro: sin jurisdicción no se gestiona nada de nadie."""
        assert not Report.objects.for_user(factory.create()).exists()


class TestImmutability:
    def test_report_municipality_cannot_be_changed_through_the_api(self, two_municipalities):
        report = two_municipalities["own_reports"][0]
        client = APIClient()
        client.force_authenticate(report.author)

        response = client.patch(
            f"/api/reports/{report.id}/",
            {"municipality": two_municipalities["other"].pk, "description": "Editado"},
            format="json",
        )

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.municipality == two_municipalities["own"]

    def test_user_municipality_cannot_be_changed_through_the_api(self, two_municipalities):
        agent = MunicipalAgentFactory.create(municipality=two_municipalities["own"])
        client = APIClient()
        client.force_authenticate(agent)

        response = client.patch(
            "/api/users/me/",
            {"municipality": two_municipalities["other"].pk},
            format="json",
        )

        assert response.status_code == 200
        agent.refresh_from_db()
        assert agent.municipality == two_municipalities["own"]

    def test_the_municipality_of_a_new_report_comes_from_the_server(
        self,
        two_municipalities,
    ):
        """El cliente no elige jurisdicción: la decide el área de cobertura.

        El body pide explícitamente el otro municipio y se ignora: manda dónde
        cayó el reporte, no lo que diga el cliente.
        """
        own = two_municipalities["own"]
        own.latitude, own.longitude, own.coverage_radius_km = -32.41, -63.24, 15
        own.save()
        other = two_municipalities["other"]
        other.latitude, other.longitude, other.coverage_radius_km = -31.42, -64.19, 20
        other.save()
        citizen = UserFactory.create()
        client = APIClient()
        client.force_authenticate(citizen)

        response = client.post(
            "/api/reports/",
            {
                "description": "Bache profundo",
                "category": Report.Category.BACHE,
                "latitude": "-32.41",
                "longitude": "-63.24",
                "photo": _one_pixel_png(),
                "municipality": two_municipalities["other"].pk,
            },
            format="multipart",
        )

        assert response.status_code == 201
        created = Report.objects.get(pk=response.data["id"])
        assert created.municipality == two_municipalities["own"]


def _one_pixel_png():
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, format="PNG")
    return SimpleUploadedFile("report.png", buffer.getvalue(), content_type="image/png")
