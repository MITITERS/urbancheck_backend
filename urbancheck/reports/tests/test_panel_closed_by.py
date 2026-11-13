"""Qué cerró un operario, para el perfil que el panel abre desde su nombre.

El agente y el administrador llegan al operario igual que al vecino y al
validador: desde su nombre en el reporte. Lo que cambia es qué se lista detrás
—al vecino lo que reportó, al validador lo que decidió, al operario lo que
cerró— y este filtro es esa lista.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionEvidenceFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/panel/reports/"

HTTP_OK = 200


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
def agent_client(municipality) -> APIClient:
    client = APIClient()
    client.force_authenticate(MunicipalAgentFactory.create(municipality=municipality))
    return client


def closed(operator, *, status=Report.Status.RESUELTO_PENDIENTE, municipality=None):
    """Un reporte que ese operario cerró."""
    area = operator.operational_area
    report = ReportFactory.create(
        municipality=municipality or area.municipality,
        operational_area=area,
        status=status,
    )
    ResolutionEvidenceFactory.create(
        report=report,
        operator=operator,
        operational_area=area,
    )
    return report


class TestClosedByFilter:
    def test_it_lists_what_that_operator_closed(self, agent_client, operator):
        report = closed(operator)

        response = agent_client.get(LIST_URL, {"closed_by": operator.pk})

        assert response.status_code == HTTP_OK
        assert [row["id"] for row in response.data["results"]] == [report.pk]

    def test_each_row_says_when_this_operator_closed_it(self, agent_client, operator):
        report = closed(operator)
        evidence = report.resolution_evidences.get()

        row = agent_client.get(LIST_URL, {"closed_by": operator.pk}).data["results"][0]

        # ``response.data`` trae el objeto de Python, no el JSON serializado.
        assert row["closure"]["closed_at"] == evidence.created_at

    def test_what_a_teammate_closed_is_not_listed(self, agent_client, operator, area):
        """El perfil es de la persona, no del área: firma quien cerró."""
        teammate = OperatorFactory.create(operational_area=area)
        closed(teammate)
        mine = closed(operator)

        response = agent_client.get(LIST_URL, {"closed_by": operator.pk})

        assert [row["id"] for row in response.data["results"]] == [mine.pk]

    def test_a_report_that_operator_never_closed_is_not_listed(
        self,
        agent_client,
        operator,
        area,
    ):
        ReportFactory.create(
            municipality=area.municipality,
            operational_area=area,
            status=Report.Status.EN_PROCESO,
        )

        assert agent_client.get(LIST_URL, {"closed_by": operator.pk}).data["count"] == 0

    def test_a_report_closed_twice_is_listed_once(self, agent_client, operator):
        """Tras una apelación hay dos evidencias suyas sobre el mismo reporte.

        Va por subconsulta y no por ``JOIN`` justamente por esto: duplicada, la
        fila haría mentir al contador del paginado.
        """
        report = closed(operator)
        ResolutionEvidenceFactory.create(
            report=report,
            operator=operator,
            operational_area=operator.operational_area,
        )

        response = agent_client.get(LIST_URL, {"closed_by": operator.pk})

        assert response.data["count"] == 1
        assert [row["id"] for row in response.data["results"]] == [report.pk]

    def test_the_row_carries_the_most_recent_closure(self, agent_client, operator):
        """De las dos, la fecha es la del último cierre: es el que está vigente.

        Al revés que ``validated_by``, que toma la decisión más vieja porque un
        reporte reactivado vuelve a pasar por *Reportado*.
        """
        report = closed(operator)
        second = ResolutionEvidenceFactory.create(
            report=report,
            operator=operator,
            operational_area=operator.operational_area,
        )

        row = agent_client.get(LIST_URL, {"closed_by": operator.pk}).data["results"][0]

        assert row["closure"]["closed_at"] == second.created_at

    def test_without_the_filter_no_row_carries_a_closure(self, agent_client, operator):
        """Sin operario por el que preguntar, no hay cierre del que hablar."""
        closed(operator)

        row = agent_client.get(LIST_URL).data["results"][0]

        assert row["closure"] is None

    def test_it_shows_the_current_status_and_not_the_one_at_closing_time(
        self,
        agent_client,
        operator,
    ):
        """Un cierre objetado volvió a *En proceso* (US-048) y se ve así."""
        report = closed(operator, status=Report.Status.EN_PROCESO)

        row = agent_client.get(LIST_URL, {"closed_by": operator.pk}).data["results"][0]

        assert row["id"] == report.pk
        assert row["status"] == Report.Status.EN_PROCESO


class TestJurisdiction:
    def test_an_agent_only_sees_what_that_operator_closed_in_their_municipality(
        self,
        agent_client,
        municipality,
    ):
        """El filtro se aplica sobre el queryset ya acotado por jurisdicción.

        Mismo criterio que ``author`` y ``validated_by``: el perfil no puede ser
        una puerta lateral a los reportes de otro municipio (US-034).
        """
        elsewhere = MunicipalityFactory.create()
        outsider = OperatorFactory.create(
            operational_area=OperationalAreaFactory.create(municipality=elsewhere),
        )
        closed(outsider)
        mine = closed(
            OperatorFactory.create(
                operational_area=OperationalAreaFactory.create(
                    municipality=municipality,
                ),
            ),
        )

        # Preguntar por el operario ajeno no devuelve su trabajo.
        assert agent_client.get(LIST_URL, {"closed_by": outsider.pk}).data["count"] == 0
        # Y el propio se sigue viendo.
        response = agent_client.get(LIST_URL)
        assert mine.pk in [row["id"] for row in response.data["results"]]

    def test_the_platform_admin_reaches_it_too(self, operator):
        """El administrador ve todas las jurisdicciones, también esta lista."""
        report = closed(operator)
        client = APIClient()
        client.force_authenticate(PlatformAdminFactory.create())

        response = client.get(LIST_URL, {"closed_by": operator.pk})

        assert response.status_code == HTTP_OK
        assert [row["id"] for row in response.data["results"]] == [report.pk]
