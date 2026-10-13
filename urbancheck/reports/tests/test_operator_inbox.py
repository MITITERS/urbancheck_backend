"""US-045 — bandeja de trabajo del operario en la app móvil."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/operator/reports/"

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404


def detail(report_id: int) -> str:
    return f"{LIST_URL}{report_id}/"


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def area(municipality):
    return OperationalAreaFactory.create(municipality=municipality)


@pytest.fixture
def operator(area):
    return OperatorFactory.create(operational_area=area)


@pytest.fixture
def client(operator) -> APIClient:
    api = APIClient()
    api.force_authenticate(operator)
    return api


def assigned(area, *, status=Report.Status.EN_PROCESO, assigned_at=None):
    return ReportFactory.create(
        municipality=area.municipality,
        operational_area=area,
        status=status,
        area_assigned_at=assigned_at or timezone.now(),
    )


class TestInbox:
    def test_it_lists_the_work_of_my_area_with_what_the_screen_needs(
        self,
        client,
        area,
    ):
        """Escenario 1."""
        report = assigned(area)

        response = client.get(LIST_URL)

        assert response.status_code == HTTP_OK
        row = response.data["results"][0]
        assert row["id"] == report.pk
        assert row["photo"]
        assert row["category"] == report.category
        assert row["description"] == report.description

    def test_the_oldest_assignment_comes_first(self, client, area):
        """Escenario 2: el trabajo más demorado, a la vista."""
        now = timezone.now()
        newest = assigned(area, assigned_at=now)
        oldest = assigned(area, assigned_at=now - timedelta(days=10))

        results = client.get(LIST_URL).data["results"]

        assert [row["id"] for row in results] == [oldest.pk, newest.pk]

    def test_another_area_of_my_own_municipality_does_not_appear(
        self,
        client,
        area,
        municipality,
    ):
        """Escenario 5."""
        mine = assigned(area)
        assigned(OperationalAreaFactory.create(municipality=municipality))

        results = client.get(LIST_URL).data["results"]

        assert [row["id"] for row in results] == [mine.pk]

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
            Report.Status.RESUELTO,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
        ],
    )
    def test_only_reports_in_progress_are_listed(self, client, area, status):
        """Escenario 6."""
        assigned(area, status=status)

        assert client.get(LIST_URL).data["results"] == []

    def test_an_empty_inbox_answers_with_an_empty_list(self, client):
        """Escenario 9: la app dibuja el estado vacío con esto."""
        response = client.get(LIST_URL)

        assert response.status_code == HTTP_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_a_reassigned_report_leaves_the_inbox(self, client, area, municipality):
        """Escenario 10."""
        report = assigned(area)
        report.operational_area = OperationalAreaFactory.create(
            municipality=municipality,
        )
        report.save(update_fields=["operational_area"])

        assert client.get(LIST_URL).data["results"] == []


class TestDetail:
    def test_it_carries_the_photo_description_category_and_location(
        self,
        client,
        area,
    ):
        """Escenarios 3 y 4: con la ubicación se abre el mapa del dispositivo."""
        report = assigned(area)

        response = client.get(detail(report.pk))

        assert response.status_code == HTTP_OK
        assert response.data["photo"]
        assert response.data["description"] == report.description
        assert response.data["latitude"] is not None
        assert response.data["longitude"] is not None
        assert response.data["address"] == report.address

    def test_a_report_of_another_area_answers_404(self, client, municipality):
        """Escenario 7: mismo criterio de US-034."""
        elsewhere = assigned(OperationalAreaFactory.create(municipality=municipality))

        assert client.get(detail(elsewhere.pk)).status_code == HTTP_NOT_FOUND

    def test_an_unassigned_report_of_my_municipality_answers_404(
        self,
        client,
        municipality,
    ):
        unassigned = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
        )

        assert client.get(detail(unassigned.pk)).status_code == HTTP_NOT_FOUND

    def test_a_report_that_left_the_inbox_still_opens(self, client, area):
        """El filtro de estado es del listado: el detalle no se rompe en la mano."""
        report = assigned(area, status=Report.Status.RESUELTO)

        assert client.get(detail(report.pk)).status_code == HTTP_OK


class TestScope:
    @pytest.mark.parametrize(
        "path",
        ["/api/reports/", "/api/reports/map/", "/api/panel/reports/"],
    )
    def test_the_operator_reaches_neither_the_feed_the_map_nor_the_panel(
        self,
        client,
        path,
    ):
        """Escenario 8."""
        assert client.get(path).status_code == HTTP_FORBIDDEN

    def test_the_operator_cannot_create_comment_or_like(self, client, area):
        """Escenario 8, segunda mitad."""
        report = assigned(area)

        assert client.post("/api/reports/", {}).status_code == HTTP_FORBIDDEN
        assert client.post(
            f"/api/reports/{report.pk}/comments/",
            {"text": "hola"},
            format="json",
        ).status_code == HTTP_FORBIDDEN
        liked = client.post(f"/api/reports/{report.pk}/like/")
        assert liked.status_code == HTTP_FORBIDDEN

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory],
        ids=["ciudadano", "validador"],
    )
    def test_nobody_else_reaches_the_inbox(self, factory):
        api = APIClient()
        api.force_authenticate(factory.create())

        assert api.get(LIST_URL).status_code == HTTP_FORBIDDEN


class TestBlockedAccounts:
    def test_a_deactivated_operator_is_told_why(self, operator):
        """Escenario 11, primera mitad."""
        operator.is_work_account_active = False
        operator.save(update_fields=["is_work_account_active"])
        api = APIClient()
        api.force_authenticate(operator)

        response = api.get(LIST_URL)

        assert response.status_code == HTTP_FORBIDDEN
        assert "operario" in response.data["detail"].lower()

    def test_an_operator_of_a_deactivated_area_is_told_why(self, operator, area):
        """Escenario 11, segunda mitad."""
        area.is_active = False
        area.save(update_fields=["is_active"])
        api = APIClient()
        api.force_authenticate(operator)

        response = api.get(LIST_URL)

        assert response.status_code == HTTP_FORBIDDEN
        assert "área" in response.data["detail"]
