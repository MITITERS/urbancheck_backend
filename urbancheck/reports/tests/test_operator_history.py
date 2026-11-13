"""US-046 — el historial de trabajos resueltos del operario.

El equivalente de «Mis reportes» del vecino para una cuenta de trabajo: el
vecino ve lo que reportó, el operario lo que cerró. Se apoya en la misma
evidencia que ya escribe el cierre, así que acá no hay estado nuevo que
mantener: lo que se prueba es a quién le pertenece cada fila.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionEvidenceFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HISTORY_URL = "/api/operator/reports/history/"
LIST_URL = "/api/operator/reports/"

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404


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


def closed_by(operator, *, status=Report.Status.RESUELTO_PENDIENTE, at=None, area=None):
    """Un reporte del área del operario que él mismo cerró.

    Escribe la evidencia directamente en vez de pasar por el endpoint de cierre:
    lo que se prueba acá es la lectura del historial, y armar cada caso con una
    subida de foto y una verificación de proximidad no lo haría más cierto.
    """
    area = area or operator.operational_area
    report = ReportFactory.create(
        municipality=area.municipality,
        operational_area=area,
        status=status,
        area_assigned_at=timezone.now(),
    )
    evidence = ResolutionEvidenceFactory.create(
        report=report,
        operator=operator,
        operational_area=area,
    )
    if at is not None:
        # ``created_at`` es ``auto_now_add``: la única forma de fechar el cierre
        # en el pasado es actualizarlo después de creado.
        type(evidence).objects.filter(pk=evidence.pk).update(created_at=at)
    return report


class TestHistory:
    def test_it_lists_what_i_closed_with_what_the_row_shows(self, client, operator):
        report = closed_by(operator)

        response = client.get(HISTORY_URL)

        assert response.status_code == HTTP_OK
        assert response.data["count"] == 1
        row = response.data["results"][0]
        assert row["id"] == report.pk
        assert row["category"] == report.category
        assert row["description"] == report.description
        assert row["photo"]
        assert row["resolved_at"] is not None

    def test_the_most_recent_closure_comes_first(self, client, operator):
        """Al revés que la bandeja: es un registro, no una cola de pendientes."""
        now = timezone.now()
        old = closed_by(operator, at=now - timedelta(days=9))
        recent = closed_by(operator, at=now - timedelta(hours=2))

        results = client.get(HISTORY_URL).data["results"]

        assert [row["id"] for row in results] == [recent.pk, old.pk]

    def test_what_a_teammate_closed_is_not_mine(self, client, operator, area):
        """El historial es de la persona, no del área: firma quien cerró."""
        teammate = OperatorFactory.create(operational_area=area)
        closed_by(teammate)
        mine = closed_by(operator)

        results = client.get(HISTORY_URL).data["results"]

        assert [row["id"] for row in results] == [mine.pk]

    def test_pending_work_is_not_history(self, client, area):
        """Lo que todavía no cerró está en la bandeja, no acá."""
        ReportFactory.create(
            municipality=area.municipality,
            operational_area=area,
            status=Report.Status.EN_PROCESO,
            area_assigned_at=timezone.now(),
        )

        assert client.get(HISTORY_URL).data["results"] == []

    def test_an_empty_history_answers_with_an_empty_list(self, client):
        """La app dibuja el estado vacío con esto, no con un error."""
        response = client.get(HISTORY_URL)

        assert response.status_code == HTTP_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_it_shows_the_current_status_and_not_the_one_at_closing_time(
        self,
        client,
        operator,
    ):
        """Un cierre objetado volvió a *En proceso* (US-048) y se ve así.

        Es la razón por la que el historial serializa el estado del reporte en
        lugar de dar por resuelto todo lo que tiene evidencia: dejarlo como
        «resuelto» le escondería al operario justamente el trabajo que le
        volvió.
        """
        report = closed_by(operator, status=Report.Status.EN_PROCESO)

        row = client.get(HISTORY_URL).data["results"][0]

        assert row["id"] == report.pk
        assert row["status"] == Report.Status.EN_PROCESO

    def test_a_report_closed_twice_appears_once(self, client, operator):
        """Tras una apelación hay **dos** evidencias suyas sobre el mismo reporte.

        El recorte va por subconsulta y no por ``JOIN`` justamente por esto: con
        el ``JOIN`` la fila saldría duplicada y el contador del listado mentiría.
        """
        report = closed_by(operator)
        ResolutionEvidenceFactory.create(
            report=report,
            operator=operator,
            operational_area=operator.operational_area,
        )

        response = client.get(HISTORY_URL)

        assert response.data["count"] == 1
        assert [row["id"] for row in response.data["results"]] == [report.pk]

    def test_the_row_carries_the_date_of_my_last_closure(self, client, operator):
        """De las dos evidencias, la fecha que se muestra es la del último cierre."""
        now = timezone.now()
        report = closed_by(operator, at=now - timedelta(days=30))
        second = ResolutionEvidenceFactory.create(
            report=report,
            operator=operator,
            operational_area=operator.operational_area,
        )

        row = client.get(HISTORY_URL).data["results"][0]

        assert row["resolved_at"][:10] == second.created_at.date().isoformat()


class TestTransferredOperator:
    """Un operario trasladado conserva lo que hizo antes (US-044, escenario 5).

    La evidencia guarda el área **del momento del cierre** para eso mismo, así
    que el historial no puede recortarse por el área de hoy.
    """

    @pytest.fixture
    def transferred(self, operator, municipality):
        report = closed_by(operator, status=Report.Status.RESUELTO)
        operator.operational_area = OperationalAreaFactory.create(
            municipality=municipality,
        )
        operator.save(update_fields=["operational_area"])
        return report

    def test_the_work_of_my_former_area_stays_in_my_history(
        self,
        client,
        transferred,
    ):
        results = client.get(HISTORY_URL).data["results"]

        assert [row["id"] for row in results] == [transferred.pk]

    def test_and_it_still_opens(self, client, transferred):
        """Toda fila del historial tiene que poder abrirse, o el listado miente."""
        assert client.get(f"{LIST_URL}{transferred.pk}/").status_code == HTTP_OK

    def test_but_it_is_no_longer_in_my_inbox(self, client, transferred):
        """Haberlo cerrado no lo devuelve a la cola de trabajo del área nueva."""
        assert client.get(LIST_URL).data["results"] == []


class TestScope:
    def test_a_report_of_another_area_that_i_never_closed_still_answers_404(
        self,
        client,
        municipality,
    ):
        """Ensanchar el detalle con el historial no abrió el resto (escenario 7)."""
        elsewhere = ReportFactory.create(
            municipality=municipality,
            operational_area=OperationalAreaFactory.create(municipality=municipality),
            status=Report.Status.EN_PROCESO,
        )

        assert client.get(f"{LIST_URL}{elsewhere.pk}/").status_code == HTTP_NOT_FOUND

    def test_closing_it_once_does_not_let_me_close_it_again_from_elsewhere(
        self,
        client,
        operator,
        municipality,
    ):
        """El cierre sigue acotado al área actual, aunque el detalle se abra."""
        report = closed_by(operator, status=Report.Status.EN_PROCESO)
        operator.operational_area = OperationalAreaFactory.create(
            municipality=municipality,
        )
        operator.save(update_fields=["operational_area"])

        response = client.post(f"{LIST_URL}{report.pk}/resolve/", {})

        assert response.status_code == HTTP_NOT_FOUND

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory],
        ids=["ciudadano", "validador"],
    )
    def test_nobody_else_reaches_the_history(self, factory):
        api = APIClient()
        api.force_authenticate(factory.create())

        assert api.get(HISTORY_URL).status_code == HTTP_FORBIDDEN

    def test_a_deactivated_operator_is_told_why(self, operator):
        operator.is_work_account_active = False
        operator.save(update_fields=["is_work_account_active"])
        api = APIClient()
        api.force_authenticate(operator)

        response = api.get(HISTORY_URL)

        assert response.status_code == HTTP_FORBIDDEN
        assert "operario" in response.data["detail"].lower()
