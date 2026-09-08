"""US-039 — gestión de áreas operativas municipales."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.models import OperationalArea
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/operational-areas/"

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405


def detail(area_id: int, suffix: str = "") -> str:
    return f"{LIST_URL}{area_id}/{suffix}"


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def agent(municipality):
    return MunicipalAgentFactory.create(municipality=municipality)


@pytest.fixture
def client(agent) -> APIClient:
    api = APIClient()
    api.force_authenticate(agent)
    return api


VALID_PAYLOAD = {
    "name": "Obras Públicas",
    "contact_email": "obras@municipio.gob.ar",
    "contact_phone": "3534 123456",
}


class TestCreate:
    def test_the_area_is_created_active_and_in_my_municipality(
        self,
        client,
        municipality,
    ):
        """Escenario 1: el agente no elige jurisdicción, se le asigna la suya."""
        response = client.post(LIST_URL, VALID_PAYLOAD, format="json")

        assert response.status_code == HTTP_CREATED
        assert response.data["is_active"] is True
        area = OperationalArea.objects.get(pk=response.data["id"])
        assert area.municipality == municipality

    def test_a_municipality_sent_by_the_client_is_ignored(self, client, municipality):
        """La jurisdicción se resuelve en el servidor, nunca en el body."""
        other = MunicipalityFactory.create()

        response = client.post(
            LIST_URL,
            {**VALID_PAYLOAD, "municipality_id": other.pk},
            format="json",
        )

        assert response.status_code == HTTP_CREATED
        created = OperationalArea.objects.get(pk=response.data["id"])
        assert created.municipality == municipality

    @pytest.mark.parametrize("missing", ["name", "contact_email", "contact_phone"])
    def test_every_field_is_mandatory(self, client, missing):
        """Escenario 2."""
        payload = {key: value for key, value in VALID_PAYLOAD.items() if key != missing}

        response = client.post(LIST_URL, payload, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert missing in response.data
        assert not OperationalArea.objects.exists()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("contact_email", "no-es-un-mail"),
            ("contact_phone", "llamar al 3534-123456"),
        ],
    )
    def test_invalid_contact_formats_are_rejected(self, client, field, value):
        """Escenario 3."""
        response = client.post(
            LIST_URL,
            {**VALID_PAYLOAD, field: value},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert field in response.data

    def test_a_duplicate_name_in_my_municipality_is_rejected(
        self,
        client,
        municipality,
    ):
        """Escenario 4, primera mitad. La comparación ignora mayúsculas."""
        OperationalAreaFactory.create(municipality=municipality, name="Obras Públicas")

        response = client.post(
            LIST_URL,
            {**VALID_PAYLOAD, "name": "obras públicas"},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert "name" in response.data

    def test_the_same_name_is_allowed_in_another_municipality(self, client):
        """Escenario 4, segunda mitad: la unicidad es compuesta."""
        OperationalAreaFactory.create(
            municipality=MunicipalityFactory.create(),
            name="Obras Públicas",
        )

        response = client.post(LIST_URL, VALID_PAYLOAD, format="json")

        assert response.status_code == HTTP_CREATED


class TestEdit:
    def test_editing_contact_data_does_not_touch_assigned_reports(
        self,
        client,
        municipality,
    ):
        """Escenario 5."""
        area = OperationalAreaFactory.create(municipality=municipality)
        report = ReportFactory.create(municipality=municipality, operational_area=area)

        response = client.patch(
            detail(area.pk),
            {"name": "Obras y Servicios", "contact_email": "nuevo@municipio.gob.ar"},
            format="json",
        )

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        assert report.operational_area_id == area.pk
        area.refresh_from_db()
        assert area.name == "Obras y Servicios"

    def test_editing_cannot_move_the_area_to_another_municipality(
        self,
        client,
        municipality,
    ):
        area = OperationalAreaFactory.create(municipality=municipality)

        client.patch(
            detail(area.pk),
            {"municipality_id": MunicipalityFactory.create().pk},
            format="json",
        )

        area.refresh_from_db()
        assert area.municipality == municipality


class TestListing:
    def test_only_my_municipality_with_its_counters(self, client, municipality):
        """Escenario 6."""
        mine = OperationalAreaFactory.create(municipality=municipality)
        ReportFactory.create(municipality=municipality, operational_area=mine)
        OperationalAreaFactory.create(municipality=MunicipalityFactory.create())

        response = client.get(LIST_URL)

        assert response.status_code == HTTP_OK
        assert [row["id"] for row in response.data] == [mine.pk]
        assert response.data[0]["report_count"] == 1
        assert response.data[0]["is_active"] is True

    def test_the_listing_shows_both_states(self, client, municipality):
        active = OperationalAreaFactory.create(municipality=municipality)
        inactive = OperationalAreaFactory.create(
            municipality=municipality,
            is_active=False,
        )

        response = client.get(LIST_URL)

        assert {row["id"] for row in response.data} == {active.pk, inactive.pk}

    def test_the_assignment_dropdown_only_gets_the_active_ones(
        self,
        client,
        municipality,
    ):
        """El desplegable de US-028 pide ``?state=active``."""
        active = OperationalAreaFactory.create(municipality=municipality)
        OperationalAreaFactory.create(municipality=municipality, is_active=False)

        response = client.get(LIST_URL, {"state": "active"})

        assert [row["id"] for row in response.data] == [active.pk]


class TestDeactivation:
    def test_deactivating_keeps_the_link_of_assigned_reports(
        self,
        client,
        municipality,
    ):
        """Escenario 7."""
        area = OperationalAreaFactory.create(municipality=municipality)
        report = ReportFactory.create(municipality=municipality, operational_area=area)

        response = client.post(detail(area.pk, "deactivate/"))

        assert response.status_code == HTTP_OK
        assert response.data["is_active"] is False
        report.refresh_from_db()
        assert report.operational_area_id == area.pk

    def test_reactivating_puts_it_back_in_the_dropdown(self, client, municipality):
        """Escenario 9."""
        area = OperationalAreaFactory.create(municipality=municipality, is_active=False)

        response = client.post(detail(area.pk, "activate/"))

        assert response.status_code == HTTP_OK
        assert client.get(LIST_URL, {"state": "active"}).data[0]["id"] == area.pk

    def test_there_is_no_hard_delete(self, client, municipality):
        """Escenario 8: se rechaza y se explica que solo puede desactivarse."""
        area = OperationalAreaFactory.create(municipality=municipality)
        ReportFactory.create(municipality=municipality, operational_area=area)

        response = client.delete(detail(area.pk))

        assert response.status_code == HTTP_METHOD_NOT_ALLOWED
        assert "desactiva" in response.data["detail"]
        assert OperationalArea.objects.filter(pk=area.pk).exists()

    def test_there_is_no_hard_delete_even_without_reports(self, client, municipality):
        area = OperationalAreaFactory.create(municipality=municipality)

        assert client.delete(detail(area.pk)).status_code == HTTP_METHOD_NOT_ALLOWED


class TestAccess:
    def test_another_municipality_answers_404(self, client):
        """Escenario 10: misma respuesta que US-034, no un 403."""
        foreign = OperationalAreaFactory.create(
            municipality=MunicipalityFactory.create(),
        )

        assert client.get(detail(foreign.pk)).status_code == HTTP_NOT_FOUND
        assert client.patch(
            detail(foreign.pk),
            {"name": "Otra"},
            format="json",
        ).status_code == HTTP_NOT_FOUND

    @pytest.mark.parametrize(
        "factory",
        [ValidatorFactory, UserFactory, OperatorFactory],
        ids=["validador", "ciudadano", "operario"],
    )
    def test_unauthorized_roles_get_403(self, factory):
        """Escenario 11."""
        api = APIClient()
        api.force_authenticate(factory.create())

        assert api.get(LIST_URL).status_code == HTTP_FORBIDDEN
        created = api.post(LIST_URL, VALID_PAYLOAD, format="json")
        assert created.status_code == HTTP_FORBIDDEN

    def test_the_platform_admin_sees_every_municipality_and_chooses_one(self):
        """No está acotado a ninguna jurisdicción, así que la elige en el alta."""
        elsewhere = MunicipalityFactory.create()
        OperationalAreaFactory.create(municipality=elsewhere)
        api = APIClient()
        api.force_authenticate(PlatformAdminFactory.create())

        listing = api.get(LIST_URL)
        created = api.post(
            LIST_URL,
            {**VALID_PAYLOAD, "municipality_id": elsewhere.pk},
            format="json",
        )

        assert len(listing.data) == 1
        assert created.status_code == HTTP_CREATED
        assert created.data["municipality"]["id"] == elsewhere.pk

    def test_the_admin_must_choose_a_municipality(self):
        api = APIClient()
        api.force_authenticate(PlatformAdminFactory.create())

        response = api.post(LIST_URL, VALID_PAYLOAD, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert "municipality_id" in response.data
