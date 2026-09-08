"""US-013 — actualizar el estado de un reporte desde el panel."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory

pytestmark = pytest.mark.django_db

# Las cinco transiciones del panel, tal como las declara la historia.
PANEL_TRANSITIONS = [
    ("process", Report.Status.REPORTADO, Report.Status.EN_PROCESO),
    ("resolve", Report.Status.EN_PROCESO, Report.Status.RESUELTO),
    ("cancel", Report.Status.EN_PROCESO, Report.Status.CANCELADO),
    ("archive", Report.Status.EN_PROCESO, Report.Status.ARCHIVADO),
    ("reactivate", Report.Status.ARCHIVADO, Report.Status.REPORTADO),
]

NEEDS_REASON = {"cancel"}


def url(report_id: int, operation: str = "") -> str:
    return f"/api/panel/reports/{report_id}/{operation}"


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def agent(municipality):
    return MunicipalAgentFactory.create(municipality=municipality)


@pytest.fixture
def agent_client(agent) -> APIClient:
    client = APIClient()
    client.force_authenticate(agent)
    return client


def body(operation: str) -> dict:
    return {"reason": "Motivo de prueba"} if operation in NEEDS_REASON else {}


class TestValidTransitions:
    @pytest.mark.parametrize(("operation", "source", "target"), PANEL_TRANSITIONS)
    def test_each_declared_transition_moves_the_report(
        self,
        agent_client,
        municipality,
        operation,
        source,
        target,
    ):
        report = ReportFactory.create(municipality=municipality, status=source)

        response = agent_client.post(
            url(report.id, f"{operation}/"),
            body(operation),
            format="json",
        )

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.status == target
        assert response.data["status"] == target

    def test_processing_records_who_and_when(self, agent_client, municipality, agent):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )

        agent_client.post(url(report.id, "process/"), format="json")

        entry = ReportStatusHistory.objects.get(report=report)
        assert entry.changed_by == agent
        assert entry.previous_status == Report.Status.REPORTADO
        assert entry.status == Report.Status.EN_PROCESO
        assert entry.created_at is not None


class TestInvalidTransitions:
    @pytest.mark.parametrize(("operation", "source", "_target"), PANEL_TRANSITIONS)
    def test_a_transition_from_the_wrong_state_is_rejected_with_409(
        self,
        agent_client,
        municipality,
        operation,
        source,
        _target,
    ):
        wrong = next(s for s in Report.Status if s != source)
        report = ReportFactory.create(municipality=municipality, status=wrong)

        response = agent_client.post(
            url(report.id, f"{operation}/"),
            body(operation),
            format="json",
        )

        assert response.status_code == 409
        assert response.data["current_status"] == wrong
        report.refresh_from_db()
        assert report.status == wrong

    @pytest.mark.parametrize("operation", ["resolve", "cancel", "archive", "process"])
    def test_final_states_admit_no_transition(
        self,
        agent_client,
        municipality,
        operation,
    ):
        for final in (Report.Status.RESUELTO, Report.Status.CANCELADO):
            report = ReportFactory.create(municipality=municipality, status=final)

            response = agent_client.post(
                url(report.id, f"{operation}/"),
                body(operation),
                format="json",
            )

            assert response.status_code == 409
            report.refresh_from_db()
            assert report.status == final

    def test_the_panel_cannot_validate_a_pending_report(self, agent_client, municipality):
        """Pendiente → Reportado es de la app móvil (US-036), no del panel."""
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
        )

        response = agent_client.post(url(report.id, "process/"), format="json")

        assert response.status_code == 409
        assert response.data["available_transitions"] == []


class TestReason:
    def test_cancelling_without_a_reason_is_rejected(self, agent_client, municipality):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.EN_PROCESO,
        )

        response = agent_client.post(url(report.id, "cancel/"), {}, format="json")

        assert response.status_code == 400
        report.refresh_from_db()
        assert report.status == Report.Status.EN_PROCESO

    def test_the_reason_lands_in_the_history(self, agent_client, municipality):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.EN_PROCESO,
            with_history=False,
        )

        agent_client.post(
            url(report.id, "cancel/"),
            {"reason": "Obra ya ejecutada por otra vía"},
            format="json",
        )

        entry = ReportStatusHistory.objects.get(report=report)
        assert entry.reason == "Obra ya ejecutada por otra vía"

    @pytest.mark.parametrize("operation", ["process", "resolve", "archive", "reactivate"])
    def test_the_rest_do_not_require_a_reason(
        self,
        agent_client,
        municipality,
        operation,
    ):
        source = {
            "process": Report.Status.REPORTADO,
            "resolve": Report.Status.EN_PROCESO,
            "archive": Report.Status.EN_PROCESO,
            "reactivate": Report.Status.ARCHIVADO,
        }[operation]
        report = ReportFactory.create(municipality=municipality, status=source)

        response = agent_client.post(url(report.id, f"{operation}/"), format="json")

        assert response.status_code == 200


class TestJurisdiction:
    @pytest.mark.parametrize(("operation", "source", "_target"), PANEL_TRANSITIONS)
    def test_no_transition_is_possible_on_another_municipality(
        self,
        agent_client,
        operation,
        source,
        _target,
    ):
        foreign = ReportFactory.create(
            municipality=MunicipalityFactory.create(),
            status=source,
        )

        response = agent_client.post(
            url(foreign.id, f"{operation}/"),
            body(operation),
            format="json",
        )

        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.status == source


class TestDetail:
    def test_detail_offers_only_the_transitions_available_now(
        self,
        agent_client,
        municipality,
    ):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.EN_PROCESO,
        )

        response = agent_client.get(url(report.id, ""))

        operations = {t["operation"] for t in response.data["available_transitions"]}
        assert operations == {"resolver", "cancelar", "archivar"}

    def test_a_pending_report_offers_no_action_in_the_panel(
        self,
        agent_client,
        municipality,
    ):
        """Escenario 5: el reporte aguarda validación en terreno."""
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
        )

        response = agent_client.get(url(report.id, ""))

        assert response.data["available_transitions"] == []

    def test_detail_carries_the_history_in_chronological_order(
        self,
        agent_client,
        municipality,
    ):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        agent_client.post(url(report.id, "process/"), format="json")
        agent_client.post(url(report.id, "archive/"), format="json")

        response = agent_client.get(url(report.id, ""))

        history = response.data["status_history"]
        assert len(history) == 2
        assert history[0]["status"] == Report.Status.ARCHIVADO
        assert history[-1]["status"] == Report.Status.EN_PROCESO


class TestPublicVisibility:
    @pytest.mark.parametrize(
        "status",
        [Report.Status.CANCELADO, Report.Status.ARCHIVADO],
    )
    def test_cancelled_and_archived_leave_the_public_feed_and_map(
        self,
        municipality,
        status,
    ):
        hidden = ReportFactory.create(municipality=municipality, status=status)
        visible = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
        )
        client = APIClient()
        client.force_authenticate(visible.author)

        feed = client.get("/api/reports/")
        map_view = client.get("/api/reports/map/")

        feed_ids = {row["id"] for row in feed.data["results"]}
        map_ids = {row["id"] for row in map_view.data["results"]}
        assert hidden.id not in feed_ids
        assert hidden.id not in map_ids
        assert visible.id in feed_ids

    def test_the_author_still_sees_their_own_cancelled_report(self, municipality):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.CANCELADO,
        )
        client = APIClient()
        client.force_authenticate(report.author)

        own = client.get("/api/reports/", {"mine": "true"})
        detail = client.get(f"/api/reports/{report.id}/")

        assert report.id in {row["id"] for row in own.data["results"]}
        assert detail.status_code == 200


class TestThePlatformAdminCanAlsoTransition:
    """Opera la plataforma entera, incluidos los reportes de cualquier municipio.

    La transición se registra con ``Actor.MUNICIPAL_AGENT`` igual que la del
    agente: el actor nombra la operación del panel, no quién la ejecutó. Quién la
    ejecutó queda en ``changed_by``, y eso es lo que se verifica acá.
    """

    @pytest.fixture
    def admin(self):
        return PlatformAdminFactory.create()

    @pytest.fixture
    def admin_client(self, admin) -> APIClient:
        client = APIClient()
        client.force_authenticate(admin)
        return client

    @pytest.mark.parametrize(("operation", "source", "target"), PANEL_TRANSITIONS)
    def test_it_runs_every_panel_transition(
        self,
        admin_client,
        municipality,
        operation,
        source,
        target,
    ):
        report = ReportFactory.create(municipality=municipality, status=source)

        response = admin_client.post(url(report.id, f"{operation}/"), body(operation))

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.status == target

    def test_it_reaches_a_report_of_any_municipality(self, admin_client):
        """No está acotado a un municipio, así que ninguno le es ajeno."""
        elsewhere = ReportFactory.create(
            municipality=MunicipalityFactory.create(),
            status=Report.Status.REPORTADO,
        )

        response = admin_client.post(url(elsewhere.id, "process/"))

        assert response.status_code == 200
        elsewhere.refresh_from_db()
        assert elsewhere.status == Report.Status.EN_PROCESO

    def test_the_history_records_who_did_it(self, admin_client, admin, municipality):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
        )

        admin_client.post(url(report.id, "process/"))

        last = ReportStatusHistory.objects.filter(report=report).latest("id")
        assert last.changed_by == admin
