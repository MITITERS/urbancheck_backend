"""US-046, US-047 y US-048 — cierre en terreno, confirmación y apelación."""

from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.notifications.models import Notification
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.resolution import run_confirmation
from urbancheck.reports.state_machine import Origin
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

HERE = {"latitude": "-32.410300", "longitude": "-63.240000"}
# A unos 300 km: bien afuera del radio de 50 metros de US-036.
FAR = {"latitude": "-30.000000", "longitude": "-61.000000"}


def photo(name="work.jpg") -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color=(10, 120, 60)).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


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
def operator_client(operator) -> APIClient:
    client = APIClient()
    client.force_authenticate(operator)
    return client


@pytest.fixture
def in_progress(area):
    """Un reporte en gestión, asignado al área del operario y ubicado en HERE."""
    return ReportFactory.create(
        municipality=area.municipality,
        operational_area=area,
        status=Report.Status.EN_PROCESO,
        latitude=HERE["latitude"],
        longitude=HERE["longitude"],
        area_assigned_at=timezone.now(),
    )


def resolve_url(report_id: int) -> str:
    return f"/api/operator/reports/{report_id}/resolve/"


def close(client, report, **overrides):
    payload = {
        "photo": photo(),
        "description": "Se rellenó el bache con asfalto en frío.",
        **HERE,
        **overrides,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    return client.post(resolve_url(report.pk), payload, format="multipart")


class TestOperatorCloses:
    def test_it_leaves_the_report_pending_confirmation(
        self,
        operator_client,
        in_progress,
        operator,
        area,
    ):
        """Escenario 1: el cierre del operario **no** lleva a Resuelto."""
        response = close(operator_client, in_progress)

        assert response.status_code == HTTP_OK
        in_progress.refresh_from_db()
        assert in_progress.status == Report.Status.RESUELTO_PENDIENTE
        assert in_progress.closed_at is not None

        evidence = ResolutionEvidence.objects.get(report=in_progress)
        assert evidence.operator == operator
        assert evidence.operational_area == area
        assert evidence.description.startswith("Se rellenó")

    def test_the_evidence_and_the_transition_share_one_transaction(
        self,
        operator_client,
        in_progress,
    ):
        """No puede existir un cierre sin parte, ni un parte sin cierre."""
        close(operator_client, in_progress)

        pending = Report.objects.filter(status=Report.Status.RESUELTO_PENDIENTE)
        for report in pending:
            assert report.resolution_evidences.exists()

    @pytest.mark.parametrize("missing", ["photo", "description"])
    def test_photo_and_description_are_mandatory(
        self,
        operator_client,
        in_progress,
        missing,
    ):
        """Escenarios 2 y 3."""
        response = close(operator_client, in_progress, **{missing: None})

        assert response.status_code == HTTP_BAD_REQUEST
        assert missing in response.data
        in_progress.refresh_from_db()
        assert in_progress.status == Report.Status.EN_PROCESO

    def test_it_must_be_registered_from_the_place(self, operator_client, in_progress):
        """Escenario 5: mismo radio que la validación en terreno de US-036."""
        response = close(operator_client, in_progress, **FAR)

        assert response.status_code == HTTP_BAD_REQUEST
        assert response.data["code"] == "too_far"
        assert response.data["radius_meters"] == 50  # noqa: PLR2004
        in_progress.refresh_from_db()
        assert in_progress.status == Report.Status.EN_PROCESO
        assert not ResolutionEvidence.objects.exists()

    def test_without_coordinates_it_is_rejected(self, operator_client, in_progress):
        """Escenario 6: sin ubicación no se puede cerrar."""
        response = operator_client.post(
            resolve_url(in_progress.pk),
            {"photo": photo(), "description": "Listo."},
            format="multipart",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        in_progress.refresh_from_db()
        assert in_progress.status == Report.Status.EN_PROCESO

    def test_a_report_of_another_area_answers_404(self, operator_client, municipality):
        """Escenario 10, primera mitad."""
        elsewhere = ReportFactory.create(
            municipality=municipality,
            operational_area=OperationalAreaFactory.create(municipality=municipality),
            status=Report.Status.EN_PROCESO,
            latitude=HERE["latitude"],
            longitude=HERE["longitude"],
        )

        assert close(operator_client, elsewhere).status_code == HTTP_NOT_FOUND

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
    def test_only_a_report_in_progress_can_be_closed(
        self,
        operator_client,
        area,
        status,
    ):
        """Escenario 10, segunda mitad."""
        report = ReportFactory.create(
            municipality=area.municipality,
            operational_area=area,
            status=status,
            latitude=HERE["latitude"],
            longitude=HERE["longitude"],
        )

        assert close(operator_client, report).status_code == HTTP_CONFLICT

    def test_there_is_no_double_close(self, operator_client, in_progress, area):
        """Escenario 11."""
        close(operator_client, in_progress)
        other = OperatorFactory.create(operational_area=area)
        client = APIClient()
        client.force_authenticate(other)

        response = close(client, in_progress)

        assert response.status_code == HTTP_CONFLICT
        assert ResolutionEvidence.objects.filter(report=in_progress).count() == 1

    def test_the_author_is_notified_with_the_objection_window(
        self,
        operator_client,
        in_progress,
    ):
        """Escenario 9."""
        close(operator_client, in_progress)

        notification = Notification.objects.get(
            report=in_progress,
            kind=Notification.Kind.CAMBIO_ESTADO,
            new_status=Report.Status.RESUELTO_PENDIENTE,
        )
        assert notification.recipient == in_progress.author
        assert "objetar" in notification.message

    def test_it_leaves_the_operator_inbox(self, operator_client, in_progress):
        """Nota de implementación: el reporte cerrado desaparece de la bandeja."""
        assert operator_client.get("/api/operator/reports/").data["count"] == 1

        close(operator_client, in_progress)

        assert operator_client.get("/api/operator/reports/").data["count"] == 0


class TestWhoSignsTheWork:
    def test_the_citizen_sees_the_area_but_not_the_operator(
        self,
        operator_client,
        in_progress,
        area,
    ):
        """Escenario 12: mismo criterio de protección del personal de US-038."""
        close(operator_client, in_progress)
        client = APIClient()
        client.force_authenticate(in_progress.author)

        evidence = client.get(f"/api/reports/{in_progress.pk}/").data[
            "resolution_evidences"
        ][0]

        assert evidence["operational_area"] == area.name
        assert evidence["photo"]
        assert evidence["description"]
        assert "operator" not in evidence

    def test_the_panel_sees_the_operator(self, operator_client, in_progress, operator):
        """Escenario 13: el municipio audita el trabajo."""
        close(operator_client, in_progress)
        agent = MunicipalAgentFactory.create(municipality=in_progress.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        evidence = client.get(f"/api/panel/reports/{in_progress.pk}/").data[
            "resolution_evidences"
        ][0]

        assert evidence["operator"]["id"] == operator.pk

    def test_the_panel_history_says_it_was_the_operator(
        self,
        operator_client,
        in_progress,
    ):
        close(operator_client, in_progress)

        entry = ReportStatusHistory.objects.get(
            report=in_progress,
            status=Report.Status.RESUELTO_PENDIENTE,
        )
        assert entry.origin == Origin.CIERRE_OPERARIO


class TestAutomaticConfirmation:
    @pytest.fixture(autouse=True)
    def _short_window(self, settings):
        """Ventana de dos minutos: es el escenario 2 y lo que hace demostrable
        la confirmación automática en la review sin esperar una semana."""
        settings.RESOLUTION_OBJECTION_MINUTES = 2
        settings.RESOLUTION_OBJECTION_WARNING_MINUTES = 1

    @pytest.fixture
    def closed(self, operator_client, in_progress):
        close(operator_client, in_progress)
        in_progress.refresh_from_db()
        return in_progress

    def age(self, report, minutes):
        """Envejece el cierre: ``closed_at`` lo escribe la transición."""
        Report.objects.filter(pk=report.pk).update(
            closed_at=timezone.now() - timedelta(minutes=minutes),
        )
        report.refresh_from_db()

    def test_the_deadline_passing_confirms_it(self, closed):
        """Escenario 1."""
        self.age(closed, 3)

        run_confirmation()

        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO
        entry = ReportStatusHistory.objects.get(
            report=closed,
            status=Report.Status.RESUELTO,
        )
        assert entry.changed_by is None
        assert entry.origin == Origin.CONFIRMACION_AUTOMATICA

    def test_within_the_deadline_nothing_happens(self, closed):
        run_confirmation()

        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO_PENDIENTE

    def test_the_deadline_is_read_from_configuration(self, closed, settings):
        """Escenario 2."""
        self.age(closed, 3)
        settings.RESOLUTION_OBJECTION_MINUTES = 60
        run_confirmation()
        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO_PENDIENTE

        settings.RESOLUTION_OBJECTION_MINUTES = 2
        run_confirmation()

        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO

    def test_the_author_sees_the_remaining_time(self, closed):
        """Escenario 3."""
        client = APIClient()
        client.force_authenticate(closed.author)

        detail = client.get(f"/api/reports/{closed.pk}/").data

        assert detail["objection_deadline"] is not None
        assert detail["can_appeal"] is True

    def test_the_author_is_warned_before_the_deadline(self, closed):
        """Escenario 4."""
        self.age(closed, 1.5)

        run_confirmation()

        notification = Notification.objects.get(
            report=closed,
            kind=Notification.Kind.PROXIMA_CONFIRMACION,
        )
        assert notification.recipient == closed.author
        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO_PENDIENTE

    def test_the_warning_is_not_repeated(self, closed):
        self.age(closed, 1.5)

        run_confirmation()
        run_confirmation()

        assert (
            Notification.objects.filter(
                report=closed,
                kind=Notification.Kind.PROXIMA_CONFIRMACION,
            ).count()
            == 1
        )

    def test_the_task_is_idempotent(self, closed):
        """La segunda corrida no genera una transición duplicada."""
        self.age(closed, 3)

        run_confirmation()
        run_confirmation()

        assert (
            ReportStatusHistory.objects.filter(
                report=closed,
                status=Report.Status.RESUELTO,
            ).count()
            == 1
        )

    def test_the_agent_can_confirm_early(self, closed):
        """Escenario 7: queda registrada con su usuario, no como automática."""
        agent = MunicipalAgentFactory.create(municipality=closed.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        response = client.post(
            f"/api/panel/reports/{closed.pk}/confirm-resolution/",
        )

        assert response.status_code == HTTP_OK
        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO
        entry = ReportStatusHistory.objects.get(
            report=closed,
            status=Report.Status.RESUELTO,
        )
        assert entry.changed_by == agent
        assert entry.origin == Origin.MANUAL

    def test_it_stays_visible_in_the_feed_during_the_window(self, closed):
        """Escenario 9: no se oculta durante la ventana de objeción."""
        client = APIClient()
        client.force_authenticate(closed.author)

        feed = client.get("/api/reports/").data["results"]
        markers = client.get("/api/reports/map/").data["results"]

        assert closed.pk in {row["id"] for row in feed}
        assert closed.pk in {row["id"] for row in markers}


class TestAppeal:
    @pytest.fixture
    def closed(self, operator_client, in_progress):
        close(operator_client, in_progress)
        in_progress.refresh_from_db()
        return in_progress

    @pytest.fixture
    def author_client(self, closed) -> APIClient:
        client = APIClient()
        client.force_authenticate(closed.author)
        return client

    def appeal(self, client, report, **overrides):
        payload = {
            "photo": photo("appeal.jpg"),
            "reason": "El bache sigue igual que antes.",
            **overrides,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return client.post(
            f"/api/reports/{report.pk}/appeal/",
            payload,
            format="multipart",
        )

    def test_it_reopens_keeping_the_area(self, author_client, closed, area):
        """Escenario 1: el trabajo mal ejecutado le corresponde a quien lo hizo."""
        response = self.appeal(author_client, closed)

        assert response.status_code == HTTP_OK
        closed.refresh_from_db()
        assert closed.status == Report.Status.EN_PROCESO
        assert closed.operational_area == area
        assert closed.appeal_count == 1

        appeal = ResolutionAppeal.objects.get(report=closed)
        assert appeal.author == closed.author
        assert appeal.reason.startswith("El bache")

    @pytest.mark.parametrize("missing", ["photo", "reason"])
    def test_reason_and_photo_are_mandatory(self, author_client, closed, missing):
        """Escenario 2."""
        response = self.appeal(author_client, closed, **{missing: None})

        assert response.status_code == HTTP_BAD_REQUEST
        closed.refresh_from_db()
        assert closed.status == Report.Status.RESUELTO_PENDIENTE

    def test_the_agent_and_the_operator_are_notified(
        self,
        author_client,
        closed,
        operator,
    ):
        """Escenario 3."""
        agent = MunicipalAgentFactory.create(municipality=closed.municipality)

        self.appeal(author_client, closed)

        notified = set(
            Notification.objects.filter(
                report=closed,
                kind=Notification.Kind.APELACION_CIERRE,
            ).values_list("recipient_id", flat=True),
        )
        assert {agent.pk, operator.pk} <= notified
        # El autor lo dispara: no se avisa a sí mismo.
        assert closed.author_id not in notified

    def test_it_comes_back_to_the_operator_inbox(
        self,
        author_client,
        closed,
        operator_client,
    ):
        """Escenario 4."""
        assert operator_client.get("/api/operator/reports/").data["count"] == 0

        self.appeal(author_client, closed)

        results = operator_client.get("/api/operator/reports/").data["results"]
        assert [row["id"] for row in results] == [closed.pk]

    def test_it_cannot_be_appealed_once_resolved(self, author_client, closed, settings):
        """Escenario 5: el plazo venció y el reporte quedó Resuelto."""
        settings.RESOLUTION_OBJECTION_MINUTES = 1
        Report.objects.filter(pk=closed.pk).update(
            closed_at=timezone.now() - timedelta(minutes=5),
        )
        run_confirmation()

        response = self.appeal(author_client, closed)

        assert response.status_code == HTTP_CONFLICT
        assert "venció" in response.data["detail"]

    def test_only_one_appeal_per_report(self, author_client, closed, operator_client):
        """Escenario 6: el segundo cierre es definitivo."""
        self.appeal(author_client, closed)
        closed.refresh_from_db()
        close(operator_client, closed)

        closed.refresh_from_db()
        # El segundo cierre va directo a Resuelto: no abre ventana nueva.
        assert closed.status == Report.Status.RESUELTO

        response = self.appeal(author_client, closed)
        assert response.status_code == HTTP_CONFLICT
        assert ResolutionAppeal.objects.filter(report=closed).count() == 1

    def test_another_citizen_cannot_appeal(self, closed):
        """Escenario 7."""
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        response = self.appeal(client, closed)

        assert response.status_code == HTTP_FORBIDDEN
        assert not ResolutionAppeal.objects.exists()

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
            Report.Status.EN_PROCESO,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
        ],
    )
    def test_other_states_do_not_admit_an_appeal(self, area, status):
        """Escenario 8."""
        report = ReportFactory.create(
            municipality=area.municipality,
            operational_area=area,
            status=status,
        )
        client = APIClient()
        client.force_authenticate(report.author)

        response = self.appeal(client, report)

        assert response.status_code == HTTP_CONFLICT

    def test_the_rejected_evidence_is_kept(
        self,
        author_client,
        closed,
        operator_client,
    ):
        """Escenario 9: el segundo cierre no pisa al primero."""
        first = ResolutionEvidence.objects.get(report=closed)
        self.appeal(author_client, closed)
        closed.refresh_from_db()
        close(operator_client, closed)

        evidences = list(closed.resolution_evidences.order_by("created_at"))
        assert len(evidences) == 2  # noqa: PLR2004
        assert evidences[0].pk == first.pk
        # La apelación conserva el vínculo con el cierre que objetó.
        assert ResolutionAppeal.objects.get(report=closed).evidence_id == first.pk

    def test_the_panel_sees_the_appeal_with_the_objected_close(
        self,
        author_client,
        closed,
        operator,
    ):
        """Escenario 10."""
        self.appeal(author_client, closed)
        agent = MunicipalAgentFactory.create(municipality=closed.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        appeal = client.get(f"/api/panel/reports/{closed.pk}/").data[
            "resolution_appeals"
        ][0]

        assert appeal["reason"].startswith("El bache")
        assert appeal["photo"]
        assert appeal["evidence"]["operator"]["id"] == operator.pk

    def test_the_history_says_it_was_the_citizen(self, author_client, closed):
        self.appeal(author_client, closed)

        entry = ReportStatusHistory.objects.filter(
            report=closed,
            status=Report.Status.EN_PROCESO,
        ).latest("id")
        assert entry.origin == Origin.APELACION_CIUDADANO
        assert entry.changed_by == closed.author

    def test_the_second_appeal_says_the_resolution_is_final(
        self,
        author_client,
        closed,
        operator_client,
    ):
        """Escenario 6: el motivo es el tope, no el vencimiento del plazo.

        Los dos rechazos dejan el reporte en *Resuelto* y responden ``409``, así
        que es fácil confundirlos. Decir el motivo equivocado manda al vecino a
        discutir lo que no es: no llegó tarde, ya usó su única objeción.
        """
        self.appeal(author_client, closed)
        closed.refresh_from_db()
        close(operator_client, closed)

        response = self.appeal(author_client, closed)

        assert response.status_code == HTTP_CONFLICT
        assert "definitiva" in response.data["detail"]
        assert "venció" not in response.data["detail"]
