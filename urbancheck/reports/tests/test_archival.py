"""US-031 — archivado automático de reportes sin validar tras 180 días."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.reports.archival import INACTIVITY_DAYS
from urbancheck.reports.archival import WARNING_DAYS_BEFORE
from urbancheck.reports.archival import run_archival
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200

WARNING_DAY = INACTIVITY_DAYS - WARNING_DAYS_BEFORE


def stale(days: int, **kwargs) -> Report:
    """Reporte pendiente de validación creado hace ``days`` días.

    ``created_at`` es ``auto_now_add``: se reescribe con un ``update()``, que es
    la única forma de fechar hacia atrás sin tocar el modelo.
    """
    report = ReportFactory.create(
        status=Report.Status.PENDIENTE_VALIDACION,
        **kwargs,
    )
    moment = timezone.now() - timedelta(days=days)
    Report.objects.filter(pk=report.pk).update(created_at=moment)
    report.refresh_from_db()
    return report


class TestAutomaticArchival:
    def test_a_report_without_interaction_is_archived_after_the_deadline(self):
        """Escenario 1."""
        report = stale(INACTIVITY_DAYS + 1)

        run_archival()

        report.refresh_from_db()
        assert report.status == Report.Status.ARCHIVADO
        assert report.archived_at is not None

    def test_the_system_is_recorded_as_responsible(self):
        """Escenario 1: el historial dice que no lo movió una persona."""
        report = stale(INACTIVITY_DAYS + 1, with_history=False)

        run_archival()

        entry = ReportStatusHistory.objects.get(report=report)
        assert entry.previous_status == Report.Status.PENDIENTE_VALIDACION
        assert entry.status == Report.Status.ARCHIVADO
        assert entry.changed_by is None

    def test_a_report_within_the_deadline_is_left_alone(self):
        report = stale(INACTIVITY_DAYS - 1)

        run_archival()

        report.refresh_from_db()
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    @pytest.mark.parametrize(
        "interaction",
        ["like", "comment"],
        ids=["like", "comentario"],
    )
    def test_a_recent_interaction_restarts_the_clock(self, interaction):
        """"Sin likes ni comentarios": las dos cuentan como señal de vida."""
        report = stale(INACTIVITY_DAYS + 1)
        if interaction == "like":
            LikeFactory.create(report=report)
        else:
            CommentFactory.create(report=report)

        run_archival()

        report.refresh_from_db()
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    def test_an_old_interaction_does_not_save_it(self):
        report = stale(INACTIVITY_DAYS + 30)
        like = LikeFactory.create(report=report)
        type(like).objects.filter(pk=like.pk).update(
            created_at=timezone.now() - timedelta(days=INACTIVITY_DAYS + 5),
        )

        run_archival()

        report.refresh_from_db()
        assert report.status == Report.Status.ARCHIVADO

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.REPORTADO,
            Report.Status.EN_PROCESO,
            Report.Status.RESUELTO,
            Report.Status.CANCELADO,
        ],
    )
    def test_only_reports_pending_validation_are_candidates(self, status):
        """Un reporte validado ya entró en la cola del municipio."""
        report = ReportFactory.create(status=status)
        Report.objects.filter(pk=report.pk).update(
            created_at=timezone.now() - timedelta(days=INACTIVITY_DAYS + 30),
        )

        run_archival()

        report.refresh_from_db()
        assert report.status == status

    def test_the_management_command_runs_the_same_policy(self):
        report = stale(INACTIVITY_DAYS + 1)

        call_command("archive_stale_reports")

        report.refresh_from_db()
        assert report.status == Report.Status.ARCHIVADO


class TestWarning:
    def test_the_author_is_warned_seven_days_before(self):
        """Escenario 2."""
        report = stale(WARNING_DAY + 1)

        run_archival()

        notification = Notification.objects.get(
            report=report,
            kind=Notification.Kind.PROXIMO_ARCHIVADO,
        )
        assert notification.recipient == report.author
        report.refresh_from_db()
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    def test_the_warning_is_not_repeated_on_every_run(self):
        """La verificación corre a diario: el aviso sale una sola vez."""
        report = stale(WARNING_DAY + 1)

        run_archival()
        run_archival()

        assert (
            Notification.objects.filter(
                report=report,
                kind=Notification.Kind.PROXIMO_ARCHIVADO,
            ).count()
            == 1
        )

    def test_a_report_far_from_the_deadline_is_not_warned(self):
        stale(WARNING_DAY - 5)

        run_archival()

        assert not Notification.objects.filter(
            kind=Notification.Kind.PROXIMO_ARCHIVADO,
        ).exists()

    def test_a_report_past_the_deadline_is_archived_instead_of_warned(self):
        """Si la verificación no corrió por unos días, no se avisa de más."""
        report = stale(INACTIVITY_DAYS + 1)

        run_archival()

        report.refresh_from_db()
        assert report.status == Report.Status.ARCHIVADO
        assert not Notification.objects.filter(
            report=report,
            kind=Notification.Kind.PROXIMO_ARCHIVADO,
        ).exists()

    def test_the_author_is_told_when_it_was_archived(self):
        """Escenario 1: el aviso de archivado explica el motivo."""
        report = stale(INACTIVITY_DAYS + 1)

        run_archival()

        notification = Notification.objects.get(
            report=report,
            kind=Notification.Kind.CAMBIO_ESTADO,
            new_status=Report.Status.ARCHIVADO,
        )
        assert "180 días" in notification.message


class TestVisibility:
    def test_an_archived_report_leaves_the_feed_and_the_map(self):
        """Escenario 3."""
        report = stale(INACTIVITY_DAYS + 1)
        run_archival()
        client = APIClient()
        client.force_authenticate(report.author)

        feed = client.get("/api/reports/").data["results"]
        markers = client.get("/api/reports/map/").data["results"]

        assert report.pk not in {row["id"] for row in feed}
        assert report.pk not in {row["id"] for row in markers}

    def test_the_author_still_sees_it_in_their_own_history_with_the_date(self):
        """Escenario 4."""
        report = stale(INACTIVITY_DAYS + 1)
        run_archival()
        client = APIClient()
        client.force_authenticate(report.author)

        rows = client.get("/api/reports/", {"mine": "true"}).data["results"]

        row = next(entry for entry in rows if entry["id"] == report.pk)
        assert row["status"] == Report.Status.ARCHIVADO
        assert row["archived_at"] is not None


class TestManualArchivalAndReactivation:
    @pytest.mark.parametrize(
        "factory",
        [MunicipalAgentFactory, PlatformAdminFactory],
        ids=["agente", "admin"],
    )
    def test_the_panel_can_archive_a_report_in_progress_at_any_time(self, factory):
        """Escenario 5."""
        report = ReportFactory.create(status=Report.Status.EN_PROCESO)
        user = (
            factory.create(municipality=report.municipality)
            if factory is MunicipalAgentFactory
            else factory.create()
        )
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(f"/api/panel/reports/{report.pk}/archive/")

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        assert report.status == Report.Status.ARCHIVADO
        assert report.archived_at is not None

    def test_reactivating_puts_it_back_as_reported_and_visible(self):
        """Escenario 6."""
        report = stale(INACTIVITY_DAYS + 1)
        run_archival()
        agent = MunicipalAgentFactory.create(municipality=report.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        response = client.post(f"/api/panel/reports/{report.pk}/reactivate/")

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        assert report.status == Report.Status.REPORTADO

        citizen = APIClient()
        citizen.force_authenticate(report.author)
        feed = citizen.get("/api/reports/").data["results"]
        assert report.pk in {row["id"] for row in feed}

    def test_a_reactivated_report_stops_being_a_candidate(self):
        """Escenario 6: reinicia el conteo de inactividad."""
        report = stale(INACTIVITY_DAYS + 1)
        run_archival()
        agent = MunicipalAgentFactory.create(municipality=report.municipality)
        client = APIClient()
        client.force_authenticate(agent)
        client.post(f"/api/panel/reports/{report.pk}/reactivate/")

        run_archival()

        report.refresh_from_db()
        assert report.status == Report.Status.REPORTADO
