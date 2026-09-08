"""US-044 — gestión de operarios de un área operativa."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionEvidenceFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/operators/"

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405

PASSWORD = "Provisoria2026!"


def detail(operator_id: int, suffix: str = "") -> str:
    return f"{LIST_URL}{operator_id}/{suffix}"


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def area(municipality):
    return OperationalAreaFactory.create(municipality=municipality)


@pytest.fixture
def client(municipality) -> APIClient:
    api = APIClient()
    api.force_authenticate(MunicipalAgentFactory.create(municipality=municipality))
    return api


def payload(area, **overrides) -> dict:
    return {
        "name": "Ramón Operario",
        "email": "ramon@cuadrilla.gob.ar",
        "phone": "3534123456",
        "temporary_password": PASSWORD,
        "operational_area_id": area.pk,
        **overrides,
    }


class TestCreate:
    def test_the_account_is_created_with_the_operator_role_and_the_area(
        self,
        client,
        area,
        municipality,
    ):
        """Escenario 1."""
        response = client.post(LIST_URL, payload(area), format="json")

        assert response.status_code == HTTP_CREATED
        operator = User.objects.get(pk=response.data["id"])
        assert operator.role == User.Role.OPERARIO
        assert operator.operational_area == area
        # La municipalidad se deriva del área, nunca del cliente.
        assert operator.municipality == municipality

    def test_the_invitation_reuses_the_temporary_password_flow(self, client, area):
        """Mismo circuito que US-035: no se duplica el flujo."""
        response = client.post(LIST_URL, payload(area), format="json")

        operator = User.objects.get(pk=response.data["id"])
        assert operator.must_change_password is True
        assert operator.check_password(PASSWORD)
        assert "temporary_password" not in response.data

    @pytest.mark.parametrize("missing", ["name", "email", "phone"])
    def test_every_field_is_mandatory(self, client, area, missing):
        """Escenario 2, primera mitad."""
        body = payload(area)
        del body[missing]

        response = client.post(LIST_URL, body, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert missing in response.data
        assert not User.objects.filter(role=User.Role.OPERARIO).exists()

    def test_an_invalid_email_is_rejected(self, client, area):
        """Escenario 2, segunda mitad."""
        response = client.post(
            LIST_URL,
            payload(area, email="no-es-un-mail"),
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert "email" in response.data

    def test_an_email_already_in_use_is_rejected(self, client, area):
        """Escenario 3: vale para cualquier rol previo."""
        existing = UserFactory.create()

        response = client.post(
            LIST_URL,
            payload(area, email=existing.email),
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert "email" in response.data

    def test_the_area_is_mandatory(self, client, area):
        """Escenario 4, primera mitad."""
        body = payload(area)
        del body["operational_area_id"]

        response = client.post(LIST_URL, body, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert "operational_area_id" in response.data

    def test_an_inactive_area_is_rejected(self, client, municipality):
        """Escenario 4, segunda mitad."""
        inactive = OperationalAreaFactory.create(
            municipality=municipality,
            is_active=False,
        )

        response = client.post(LIST_URL, payload(inactive), format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert "desactivada" in str(response.data["operational_area_id"])

    def test_an_area_of_another_municipality_is_rejected(self, client):
        """Escenario 10, en el alta: falla como validación de campo."""
        foreign = OperationalAreaFactory.create(
            municipality=MunicipalityFactory.create(),
        )

        response = client.post(LIST_URL, payload(foreign), format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert "operational_area_id" in response.data


class TestAreaChange:
    def test_moving_the_operator_updates_the_link(self, client, area, municipality):
        """Escenario 5."""
        operator = OperatorFactory.create(operational_area=area)
        destination = OperationalAreaFactory.create(municipality=municipality)

        response = client.patch(
            detail(operator.pk),
            {"operational_area_id": destination.pk},
            format="json",
        )

        assert response.status_code == HTTP_OK
        operator.refresh_from_db()
        assert operator.operational_area == destination

    def test_past_closures_keep_the_area_that_handled_them(
        self,
        client,
        area,
        municipality,
    ):
        """Escenario 5: el cierre queda con el área del reporte.

        No con la del operario, que puede haberse mudado desde entonces.
        """
        operator = OperatorFactory.create(operational_area=area)
        closed = ReportFactory.create(
            municipality=municipality,
            operational_area=area,
            status=Report.Status.RESUELTO,
        )
        destination = OperationalAreaFactory.create(municipality=municipality)

        client.patch(
            detail(operator.pk),
            {"operational_area_id": destination.pk},
            format="json",
        )

        closed.refresh_from_db()
        assert closed.operational_area == area

    def test_it_cannot_be_moved_to_an_area_of_another_municipality(self, client, area):
        operator = OperatorFactory.create(operational_area=area)
        foreign = OperationalAreaFactory.create(
            municipality=MunicipalityFactory.create(),
        )

        response = client.patch(
            detail(operator.pk),
            {"operational_area_id": foreign.pk},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        operator.refresh_from_db()
        assert operator.operational_area == area


class TestListing:
    def test_only_my_municipality_with_area_state_and_closures(
        self,
        client,
        area,
        municipality,
    ):
        """Escenario 6."""
        mine = OperatorFactory.create(operational_area=area)
        # La cifra sale de los partes de trabajo de US-046: desde US-047 el
        # estado *Resuelto* lo produce la confirmación, no el operario.
        ResolutionEvidenceFactory.create(
            report=ReportFactory.create(
                municipality=municipality,
                operational_area=area,
                status=Report.Status.RESUELTO,
            ),
            operator=mine,
            operational_area=area,
        )
        OperatorFactory.create()

        response = client.get(LIST_URL)

        rows = response.data["results"]
        assert [row["id"] for row in rows] == [mine.pk]
        assert rows[0]["operational_area"]["id"] == area.pk
        assert rows[0]["is_active_operator"] is True
        assert rows[0]["closed_count"] == 1
        assert rows[0]["phone"] == mine.phone

    def test_it_can_be_narrowed_to_one_area(self, client, area, municipality):
        """La ficha del área muestra solo a los suyos."""
        here = OperatorFactory.create(operational_area=area)
        OperatorFactory.create(
            operational_area=OperationalAreaFactory.create(municipality=municipality),
        )

        response = client.get(LIST_URL, {"operational_area": area.pk})

        assert [row["id"] for row in response.data["results"]] == [here.pk]


class TestDeactivation:
    def test_a_deactivated_operator_loses_access_but_keeps_its_history(
        self,
        client,
        area,
    ):
        """Escenario 7."""
        operator = OperatorFactory.create(operational_area=area)

        response = client.post(detail(operator.pk, "deactivate/"))

        assert response.status_code == HTTP_OK
        operator.refresh_from_db()
        assert operator.is_work_account_active is False
        assert operator.can_work_as_operator is False

        inbox = APIClient()
        inbox.force_authenticate(operator)
        assert inbox.get("/api/operator/reports/").status_code == HTTP_FORBIDDEN

    def test_there_is_no_hard_delete(self, client, area):
        """Escenario 8."""
        operator = OperatorFactory.create(operational_area=area)

        response = client.delete(detail(operator.pk))

        assert response.status_code == HTTP_METHOD_NOT_ALLOWED
        assert User.objects.filter(pk=operator.pk).exists()

    def test_deactivating_the_area_blocks_its_operators(self, client, area):
        """Escenario 9: el operario sigue habilitado, su área no."""
        operator = OperatorFactory.create(operational_area=area)
        area.is_active = False
        area.save(update_fields=["is_active"])

        operator.refresh_from_db()
        assert operator.is_work_account_active is True
        assert operator.can_work_as_operator is False


class TestAccess:
    def test_another_municipality_answers_404(self, client):
        """Escenario 10."""
        foreign = OperatorFactory.create()

        assert client.get(detail(foreign.pk)).status_code == HTTP_NOT_FOUND
        deactivated = client.post(detail(foreign.pk, "deactivate/"))
        assert deactivated.status_code == HTTP_NOT_FOUND

    @pytest.mark.parametrize(
        "factory",
        [ValidatorFactory, OperatorFactory, UserFactory],
        ids=["validador", "operario", "ciudadano"],
    )
    def test_unauthorized_roles_get_403(self, factory, area):
        """Escenario 11."""
        api = APIClient()
        api.force_authenticate(factory.create())

        assert api.get(LIST_URL).status_code == HTTP_FORBIDDEN
        created = api.post(LIST_URL, payload(area), format="json")
        assert created.status_code == HTTP_FORBIDDEN
