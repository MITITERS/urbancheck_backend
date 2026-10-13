"""US-024 — publicar respuestas oficiales del municipio en un reporte."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.notifications.models import Notification
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import OfficialResponseFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_CONFLICT = 409
HTTP_BAD_REQUEST = 400

TEXT = "Vamos a reparar el bache en el plazo de 15 días hábiles."


def panel(report_id: int, suffix: str = "") -> str:
    return f"/api/panel/reports/{report_id}/{suffix}"


def publish(report_id: int) -> str:
    return panel(report_id, "official-responses/")


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


@pytest.fixture
def report(municipality):
    return ReportFactory.create(
        municipality=municipality,
        status=Report.Status.REPORTADO,
    )


class TestPublishing:
    def test_it_lands_in_the_thread_with_author_municipality_and_date(
        self,
        client,
        report,
        agent,
        municipality,
    ):
        """Escenario 1."""
        response = client.post(publish(report.pk), {"text": TEXT}, format="json")

        assert response.status_code == HTTP_OK
        published = OfficialResponse.objects.get(report=report)
        assert published.text == TEXT
        assert published.author == agent
        assert published.municipality == municipality
        assert published.created_at is not None

    @pytest.mark.parametrize(
        "status",
        [Report.Status.REPORTADO, Report.Status.EN_PROCESO],
    )
    def test_the_two_management_states_admit_it(self, client, municipality, status):
        """Escenario 1: los estados de gestión activa."""
        report = ReportFactory.create(municipality=municipality, status=status)

        assert client.post(
            publish(report.pk),
            {"text": TEXT},
            format="json",
        ).status_code == HTTP_OK

    def test_a_second_response_does_not_replace_the_first(self, client, report):
        """Escenario 2: el hilo acumula, en orden cronológico."""
        client.post(publish(report.pk), {"text": "Primera"}, format="json")
        response = client.post(publish(report.pk), {"text": "Segunda"}, format="json")

        thread = response.data["official_responses"]
        assert [entry["text"] for entry in thread] == ["Primera", "Segunda"]

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
            Report.Status.RESUELTO,
        ],
    )
    def test_the_other_states_do_not_admit_it(self, client, municipality, status):
        """Escenarios 5 y 6."""
        report = ReportFactory.create(municipality=municipality, status=status)

        response = client.post(publish(report.pk), {"text": TEXT}, format="json")

        assert response.status_code == HTTP_CONFLICT
        assert not OfficialResponse.objects.filter(report=report).exists()

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
            Report.Status.RESUELTO,
        ],
    )
    def test_the_panel_is_told_that_the_action_is_not_offered(
        self,
        client,
        municipality,
        status,
    ):
        """El panel no replica la regla: la lee del detalle."""
        report = ReportFactory.create(municipality=municipality, status=status)

        detail = client.get(panel(report.pk)).data

        assert detail["can_publish_official_response"] is False

    def test_existing_responses_stay_visible_after_resolution(
        self,
        client,
        report,
    ):
        """Escenario 6, segunda mitad."""
        client.post(publish(report.pk), {"text": TEXT}, format="json")
        report.status = Report.Status.RESUELTO
        report.save(update_fields=["status"])

        detail = client.get(panel(report.pk)).data

        assert len(detail["official_responses"]) == 1
        assert detail["can_publish_official_response"] is False

    @pytest.mark.parametrize("text", ["", "   "])
    def test_empty_content_is_rejected(self, client, report, text):
        """Escenario 9, primera mitad."""
        response = client.post(publish(report.pk), {"text": text}, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        assert not OfficialResponse.objects.exists()

    def test_content_beyond_the_maximum_is_rejected(self, client, report):
        """Escenario 9, segunda mitad."""
        response = client.post(
            publish(report.pk),
            {"text": "a" * (OfficialResponse.MAX_LENGTH + 1)},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert not OfficialResponse.objects.exists()


class TestImmutability:
    def test_there_is_no_endpoint_to_edit_or_delete_a_response(self, client, report):
        """Escenario 3: la garantía es la ausencia de la operación."""
        client.post(publish(report.pk), {"text": TEXT}, format="json")
        published = OfficialResponse.objects.get(report=report)

        for method in (client.put, client.patch):
            response = method(
                publish(report.pk),
                {"text": "Reescrito"},
                format="json",
            )
            assert response.status_code == HTTP_METHOD_NOT_ALLOWED

        assert client.delete(publish(report.pk)).status_code == HTTP_METHOD_NOT_ALLOWED
        published.refresh_from_db()
        assert published.text == TEXT

    def test_not_even_the_platform_admin_can_rewrite_one(self, report):
        """Escenario 3: incluido el administrador."""
        OfficialResponseFactory.create(report=report, text=TEXT)
        api = APIClient()
        api.force_authenticate(PlatformAdminFactory.create())

        assert api.patch(
            publish(report.pk),
            {"text": "Reescrito"},
            format="json",
        ).status_code == HTTP_METHOD_NOT_ALLOWED


class TestNotification:
    def test_the_author_is_told_that_the_municipality_answered(self, client, report):
        """Escenario 4."""
        client.post(publish(report.pk), {"text": TEXT}, format="json")

        notification = Notification.objects.get(
            report=report,
            kind=Notification.Kind.RESPUESTA_OFICIAL,
        )
        assert notification.recipient == report.author
        # El aviso nombra al municipio, nunca al agente.
        assert notification.actor is None
        assert report.municipality.city in notification.message


class TestAccess:
    def test_another_municipality_answers_404(self, client):
        """Escenario 7."""
        foreign = ReportFactory.create(
            municipality=MunicipalityFactory.create(),
            status=Report.Status.REPORTADO,
        )

        response = client.post(publish(foreign.pk), {"text": TEXT}, format="json")

        assert response.status_code == HTTP_NOT_FOUND
        assert not OfficialResponse.objects.exists()

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, OperatorFactory],
        ids=["ciudadano", "validador", "operario"],
    )
    def test_unauthorized_roles_get_403(self, factory, report):
        """Escenario 8."""
        api = APIClient()
        api.force_authenticate(factory.create())

        response = api.post(publish(report.pk), {"text": TEXT}, format="json")

        assert response.status_code == HTTP_FORBIDDEN
        assert not OfficialResponse.objects.exists()

    def test_the_platform_admin_can_publish(self, report):
        """El rótulo institucional lo produce el agente o el administrador."""
        api = APIClient()
        api.force_authenticate(PlatformAdminFactory.create())

        response = api.post(publish(report.pk), {"text": TEXT}, format="json")

        assert response.status_code == HTTP_OK
        published = OfficialResponse.objects.get(report=report)
        assert published.municipality == report.municipality


class TestWhoSignsIt:
    def test_the_citizen_sees_the_municipality_and_not_the_agent(self, report, agent):
        """Escenario 11."""
        OfficialResponseFactory.create(report=report, author=agent, text=TEXT)
        api = APIClient()
        api.force_authenticate(report.author)

        entry = api.get(f"/api/reports/{report.pk}/").data["official_responses"][0]

        assert entry["municipality"] == report.municipality.city
        assert entry["text"] == TEXT
        assert "author" not in entry

    def test_the_panel_sees_the_agent(self, client, report, agent):
        """Escenario 12."""
        OfficialResponseFactory.create(report=report, author=agent, text=TEXT)

        entry = client.get(panel(report.pk)).data["official_responses"][0]

        assert entry["author"]["id"] == agent.pk
        assert entry["created_at"] is not None


class TestListingIndicator:
    def test_the_panel_listing_flags_reports_without_an_official_response(
        self,
        client,
        municipality,
    ):
        """Escenario 13."""
        answered = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
        )
        OfficialResponseFactory.create(report=answered)
        silent = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
        )

        listing = client.get("/api/panel/reports/").data["results"]
        rows = {row["id"]: row for row in listing}

        assert rows[answered.pk]["has_official_response"] is True
        assert rows[silent.pk]["has_official_response"] is False

    def test_the_citizen_feed_carries_the_same_flag(self, report):
        """Escenario 1: la respuesta también se destaca en el feed."""
        OfficialResponseFactory.create(report=report)
        api = APIClient()
        api.force_authenticate(report.author)

        row = next(
            entry
            for entry in api.get("/api/reports/").data["results"]
            if entry["id"] == report.pk
        )

        assert row["has_official_response"] is True


class TestSeparateFromOtherBlocks:
    def test_the_thread_does_not_mix_with_the_comments(self, report, agent):
        """Escenario 10: son bloques distintos en la respuesta, no una sola lista."""
        OfficialResponseFactory.create(report=report, author=agent, text=TEXT)
        api = APIClient()
        api.force_authenticate(report.author)

        detail = api.get(f"/api/reports/{report.pk}/").data

        assert detail["comments"] == []
        assert len(detail["official_responses"]) == 1


def test_an_operator_cannot_even_read_the_citizen_detail(report):
    """US-045, escenario 8: el alcance del operario es su bandeja."""
    operator = OperatorFactory.create(
        operational_area=OperationalAreaFactory.create(
            municipality=report.municipality,
        ),
    )
    api = APIClient()
    api.force_authenticate(operator)

    assert api.get(f"/api/reports/{report.pk}/").status_code == HTTP_FORBIDDEN
