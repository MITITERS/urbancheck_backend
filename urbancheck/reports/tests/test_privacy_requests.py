"""US-043 — solicitar la revisión de una imagen con un dato personal visible."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.notifications.models import Notification
from urbancheck.reports import privacy
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.tests.factories import ReportComplaintFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionEvidenceFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

INBOX = "/api/platform/privacy-requests/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def request_review(client, report, **payload):
    return client.post(
        f"/api/reports/{report.pk}/privacy-request/",
        payload,
        format="json",
    )


def on_disk(name: str | None) -> bool:
    return bool(name) and (Path(settings.MEDIA_ROOT) / str(name)).is_file()


def listed_ids(response) -> set[int]:
    data = response.data
    rows = data["results"] if isinstance(data, dict) else data
    return {row["id"] for row in rows}


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def neighbour():
    return UserFactory.create()


@pytest.fixture
def admin():
    return PlatformAdminFactory.create()


@pytest.fixture
def report(active_municipality, author):
    return ReportFactory.create(
        author=author,
        municipality=active_municipality,
        status=Report.Status.REPORTADO,
    )


def ago(**delta):
    return timezone.now() - timedelta(**delta)


def received(complaint, when) -> None:
    """Fecha la recepción en el pasado sin tocar el reloj."""
    ReportComplaint.objects.filter(pk=complaint.pk).update(created_at=when)
    complaint.refresh_from_db()


class TestRequestingReview:
    """Escenarios 1, 3 y 9: presentar la solicitud."""

    def test_it_registers_the_reason_the_image_and_the_reception_time(
        self,
        report,
        neighbour,
    ):
        """CP-043-01 (US-043 E1)."""
        before = timezone.now()

        response = request_review(client_for(neighbour), report)

        assert response.status_code == HTTP_CREATED
        complaint = ReportComplaint.objects.get()
        assert complaint.reason == ReportComplaint.Reason.DATO_PERSONAL
        assert complaint.report == report
        assert complaint.resolution_evidence is None
        assert complaint.image_name == report.photo.name
        assert complaint.reporter == neighbour
        assert complaint.created_at >= before
        assert complaint.is_pending

    def test_the_confirmation_promises_the_24_hour_review(self, report, neighbour):
        """CP-043-02 (US-043 E1)."""
        response = request_review(client_for(neighbour), report)

        assert "24 horas" in response.data["detail"]
        received_at = parse_datetime(response.data["received_at"])
        deadline = parse_datetime(response.data["deadline"])
        complaint = ReportComplaint.objects.get()
        assert received_at == complaint.created_at
        assert deadline == complaint.created_at + timedelta(hours=24)

    def test_any_citizen_can_file_it_not_only_the_author(self, report, neighbour):
        """CP-043-23 (US-043 E3).

        Escenario 3: ni autor ni persona fotografiada, y se acepta igual.
        """
        assert neighbour != report.author

        response = request_review(client_for(neighbour), report)

        assert response.status_code == HTTP_CREATED

    def test_the_author_can_file_it_too(self, report, author):
        """CP-043-24 (US-043 E3)."""
        response = request_review(client_for(author), report)

        assert response.status_code == HTTP_CREATED

    def test_a_second_request_by_the_same_user_is_rejected_without_a_new_record(
        self,
        report,
        neighbour,
    ):
        """CP-043-56 (US-043 E9).

        Escenario 9: el reporte ya está oculto, y aun así se le dice por qué.
        """
        client = client_for(neighbour)
        request_review(client, report)

        response = request_review(client, report)

        assert response.status_code == HTTP_CONFLICT
        assert response.data["code"] == "privacy_request_pending"
        assert ReportComplaint.objects.count() == 1

    def test_another_user_can_add_theirs_on_the_same_image(self, report, neighbour):
        """CP-043-57 (US-043 E9)."""
        request_review(client_for(neighbour), report)

        response = request_review(client_for(UserFactory.create()), report)

        assert response.status_code == HTTP_CREATED
        assert ReportComplaint.objects.count() == 2  # noqa: PLR2004

    def test_the_same_user_can_file_again_after_a_decision(
        self,
        report,
        neighbour,
        admin,
    ):
        """CP-043-58 (US-043 E9)."""
        complaint = ReportComplaintFactory.create(report=report, reporter=neighbour)
        privacy.dismiss(complaint, admin=admin)

        response = request_review(client_for(neighbour), report)

        assert response.status_code == HTTP_CREATED

    def test_the_photo_of_a_resolution_evidence_can_be_reported(
        self,
        report,
        neighbour,
    ):
        """CP-043-03 (US-043 E1)."""
        evidence = ResolutionEvidenceFactory.create(report=report)

        response = request_review(client_for(neighbour), report, evidence=evidence.pk)

        assert response.status_code == HTTP_CREATED
        complaint = ReportComplaint.objects.get()
        assert complaint.resolution_evidence == evidence
        assert complaint.image_name == evidence.photo.name

    def test_the_report_photo_and_an_evidence_photo_are_different_images(
        self,
        report,
        neighbour,
    ):
        """CP-043-04 (US-043 E1)."""
        evidence = ResolutionEvidenceFactory.create(report=report)
        client = client_for(neighbour)
        request_review(client, report)

        response = request_review(client, report, evidence=evidence.pk)

        assert response.status_code == HTTP_CREATED

    def test_an_evidence_of_another_report_is_rejected(self, report, neighbour):
        """CP-043-05 (US-043 E1)."""
        foreign = ResolutionEvidenceFactory.create()

        response = request_review(client_for(neighbour), report, evidence=foreign.pk)

        assert response.status_code == HTTP_BAD_REQUEST
        assert not ReportComplaint.objects.exists()

    def test_an_image_already_removed_cannot_be_reported(self, report, neighbour):
        """CP-043-06 (US-043 E1)."""
        Report.objects.filter(pk=report.pk).update(
            photo="",
            photo_removed_at=timezone.now(),
        )

        response = request_review(client_for(neighbour), report)

        assert response.status_code == HTTP_CONFLICT
        assert response.data["code"] == "image_already_removed"

    @pytest.mark.parametrize("factory", [ValidatorFactory, MunicipalAgentFactory])
    def test_work_accounts_use_their_personal_account(self, report, factory):
        """CP-043-07 (US-043 E1)."""
        worker = factory.create(municipality=report.municipality)

        response = request_review(client_for(worker), report)

        assert response.status_code == HTTP_FORBIDDEN

    def test_the_operator_is_rejected(self, report):
        """CP-043-08 (US-043 E1)."""
        response = request_review(client_for(OperatorFactory.create()), report)

        assert response.status_code == HTTP_FORBIDDEN

    def test_it_requires_a_session(self, report):
        """CP-043-09 (US-043 E1)."""
        response = request_review(APIClient(), report)

        assert response.status_code in {401, 403}


class TestImmediateHiding:
    """Escenario 2: una solicitud, sin umbral, y el reporte deja de verse."""

    def test_one_request_hides_it_from_the_feed(self, report, neighbour):
        """CP-043-13 (US-043 E2)."""
        viewer = client_for(UserFactory.create())
        assert report.pk in listed_ids(viewer.get("/api/reports/"))

        request_review(client_for(neighbour), report)

        assert report.pk not in listed_ids(viewer.get("/api/reports/"))

    def test_it_is_hidden_from_the_map(self, report, neighbour):
        """CP-043-14 (US-043 E2)."""
        request_review(client_for(neighbour), report)

        response = client_for(UserFactory.create()).get("/api/reports/map/")

        assert report.pk not in listed_ids(response)

    def test_it_is_hidden_from_the_authors_public_profile(self, report, neighbour):
        """CP-043-15 (US-043 E2)."""
        report.author.is_public = True
        report.author.save()
        request_review(client_for(neighbour), report)

        response = client_for(UserFactory.create()).get(
            f"/api/reports/?author={report.author_id}",
        )

        assert report.pk not in listed_ids(response)

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [
            ("get", ""),
            ("get", "comments/"),
            ("post", "comments/"),
            ("post", "like/"),
        ],
    )
    def test_third_parties_cannot_open_it_by_id(
        self,
        report,
        neighbour,
        method,
        suffix,
    ):
        """CP-043-16 (US-043 E2)."""
        request_review(client_for(neighbour), report)
        client = client_for(UserFactory.create())

        response = getattr(client, method)(
            f"/api/reports/{report.pk}/{suffix}",
            {"text": "hola"},
            format="json",
        )

        assert response.status_code == HTTP_NOT_FOUND

    def test_the_author_still_sees_it_marked_as_under_review(self, report, neighbour):
        """CP-043-17 (US-043 E2)."""
        request_review(client_for(neighbour), report)
        client = client_for(report.author)

        detail = client.get(f"/api/reports/{report.pk}/")
        mine = client.get("/api/reports/?mine=true")

        assert detail.status_code == HTTP_OK
        assert detail.data["under_privacy_review"] is True
        row = next(r for r in mine.data["results"] if r["id"] == report.pk)
        assert row["under_privacy_review"] is True

    def test_an_evidence_photo_request_hides_the_whole_report(
        self,
        report,
        neighbour,
    ):
        """CP-043-18 (US-043 E2)."""
        evidence = ResolutionEvidenceFactory.create(report=report)

        request_review(client_for(neighbour), report, evidence=evidence.pk)

        response = client_for(UserFactory.create()).get("/api/reports/")
        assert report.pk not in listed_ids(response)

    def test_a_report_without_requests_is_not_under_review(self, report):
        """CP-043-19 (US-043 E2)."""
        response = client_for(report.author).get(f"/api/reports/{report.pk}/")

        assert response.data["under_privacy_review"] is False

    def test_the_panel_still_shows_it_flagged(self, report, neighbour):
        """CP-043-63 (US-043 E10).

        No es una vista pública: el agente tiene que saber por qué no se ve.
        """
        request_review(client_for(neighbour), report)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        response = client_for(agent).get(f"/api/panel/reports/{report.pk}/")

        assert response.status_code == HTTP_OK
        assert response.data["under_privacy_review"] is True


class TestVisibilityFunction:
    """La condición vive en una sola función del queryset."""

    def test_only_a_pending_request_hides(self, report, admin):
        """CP-043-20 (US-043 E2)."""
        complaint = ReportComplaintFactory.create(report=report)
        assert not Report.objects.publicly_visible().filter(pk=report.pk).exists()

        privacy.dismiss(complaint, admin=admin)

        assert Report.objects.publicly_visible().filter(pk=report.pk).exists()

    def test_it_keeps_excluding_inactive_reports(self, active_municipality):
        """CP-043-21 (US-043 E2)."""
        cancelled = ReportFactory.create(
            municipality=active_municipality,
            status=Report.Status.CANCELADO,
        )

        assert not Report.objects.publicly_visible().filter(pk=cancelled.pk).exists()

    def test_the_author_is_the_only_one_who_sees_a_held_report(self, report):
        """CP-043-22 (US-043 E2)."""
        ReportComplaintFactory.create(report=report)
        stranger = UserFactory.create()

        assert Report.objects.visible_to(report.author).filter(pk=report.pk).exists()
        assert not Report.objects.visible_to(stranger).filter(pk=report.pk).exists()


class TestAdminInbox:
    """Escenarios 4, 7 y 10: la bandeja del administrador."""

    def test_it_lists_requests_from_every_municipality(self, admin):
        """CP-043-25 (US-043 E4)."""
        here = ReportComplaintFactory.create()
        there = ReportComplaintFactory.create(
            report=ReportFactory.create(municipality=MunicipalityFactory.create()),
        )

        response = client_for(admin).get(INBOX)

        assert response.status_code == HTTP_OK
        assert listed_ids(response) == {here.pk, there.pk}

    def test_each_row_carries_image_report_reception_and_remaining_time(
        self,
        admin,
        report,
    ):
        """CP-043-26 (US-043 E4)."""
        complaint = ReportComplaintFactory.create(report=report)
        received(complaint, ago(hours=3))

        row = client_for(admin).get(INBOX).data["results"][0]

        assert row["image"]["kind"] == "report"
        assert row["image"]["url"].endswith(report.photo.name)
        assert row["report"]["id"] == report.pk
        assert row["report"]["municipality"]["id"] == report.municipality_id
        assert row["received_at"]
        remaining = row["remaining_seconds"]
        assert 21 * 3600 - 60 < remaining <= 21 * 3600
        assert row["is_overdue"] is False

    def test_they_are_ordered_by_age(self, admin):
        """CP-043-27 (US-043 E4)."""
        newer = ReportComplaintFactory.create()
        older = ReportComplaintFactory.create()
        received(newer, ago(hours=1))
        received(older, ago(hours=5))

        rows = client_for(admin).get(INBOX).data["results"]

        assert [row["id"] for row in rows] == [older.pk, newer.pk]

    def test_an_overdue_request_is_flagged_and_goes_first(self, admin):
        """CP-043-49 (US-043 E7).

        Escenario 7.
        """
        on_time = ReportComplaintFactory.create()
        overdue = ReportComplaintFactory.create()
        received(on_time, ago(hours=2))
        received(overdue, ago(hours=25))

        rows = client_for(admin).get(INBOX).data["results"]

        assert rows[0]["id"] == overdue.pk
        assert rows[0]["is_overdue"] is True
        assert rows[0]["remaining_seconds"] < 0
        assert rows[1]["is_overdue"] is False

    def test_the_deadline_counts_from_reception_not_from_resolution_activity(
        self,
        report,
        admin,
    ):
        """CP-043-50 (US-043 E7).

        Una solicitud hermana resuelta no mueve el plazo de la que queda.
        """
        complaint = ReportComplaintFactory.create(report=report)
        received(complaint, ago(hours=23))

        assert privacy.deadline_for(complaint) == complaint.created_at + timedelta(
            hours=24,
        )
        row = client_for(admin).get(INBOX).data["results"][0]
        assert row["remaining_seconds"] <= timedelta(hours=1).total_seconds()

    def test_the_deadline_follows_the_configuration(self, settings, report):
        """CP-043-51 (US-043 E7)."""
        settings.PERSONAL_DATA_REVIEW_MINUTES = 5
        complaint = ReportComplaintFactory.create(report=report)

        assert privacy.deadline_for(complaint) == complaint.created_at + timedelta(
            minutes=5,
        )
        assert privacy.describe_window() == "5 minutos"

    def test_resolved_requests_leave_the_pending_list(self, admin, report):
        """CP-043-28 (US-043 E4)."""
        complaint = ReportComplaintFactory.create(report=report)
        privacy.dismiss(complaint, admin=admin)

        response = client_for(admin).get(INBOX)

        assert listed_ids(response) == set()

    def test_it_can_be_narrowed_to_one_municipality(self, admin):
        """CP-043-29 (US-043 E4)."""
        here = ReportComplaintFactory.create()
        ReportComplaintFactory.create(
            report=ReportFactory.create(municipality=MunicipalityFactory.create()),
        )

        response = client_for(admin).get(
            f"{INBOX}?municipality={here.report.municipality_id}",
        )

        assert listed_ids(response) == {here.pk}

    def test_the_municipal_agent_sees_those_of_their_municipality(self, report):
        """CP-043-59. Decisión del usuario (21/10), contraria al escenario 10.

        El agente ve las solicitudes de su municipalidad, con la imagen: los dos
        roles tienen que ver lo denunciado (pedido del usuario, 21/10).
        """
        agent = MunicipalAgentFactory.create(municipality=report.municipality)
        mine = ReportComplaintFactory.create(report=report)
        ReportComplaintFactory.create(
            report=ReportFactory.create(municipality=MunicipalityFactory.create()),
        )

        response = client_for(agent).get(INBOX)

        assert response.status_code == HTTP_OK
        assert listed_ids(response) == {mine.pk}
        [row] = response.data["results"]
        assert row["image"]["url"]

    def test_an_agent_cannot_open_another_municipality_request(self, report):
        """CP-043-64. Igual que en el resto del panel: ``404``."""
        complaint = ReportComplaintFactory.create(report=report)
        stranger = MunicipalAgentFactory.create()

        response = client_for(stranger).get(f"{INBOX}{complaint.pk}/")

        assert response.status_code == HTTP_NOT_FOUND

    def test_the_admin_sees_the_pending_image(self, admin, report):
        """CP-043-65. Es quien decide: tiene que ver qué decide."""
        ReportComplaintFactory.create(report=report)

        [row] = client_for(admin).get(INBOX).data["results"]

        assert row["image"]["url"]

    @pytest.mark.parametrize("decision", ["remove-image", "dismiss"])
    def test_the_municipal_agent_resolves_those_of_their_municipality(
        self,
        report,
        decision,
    ):
        """CP-043-60. Decisión del usuario (21/10), contraria al escenario 10."""
        agent = MunicipalAgentFactory.create(municipality=report.municipality)
        complaint = ReportComplaintFactory.create(report=report)

        response = client_for(agent).post(f"{INBOX}{complaint.pk}/{decision}/")

        assert response.status_code == HTTP_OK
        complaint.refresh_from_db()
        assert not complaint.is_pending
        assert complaint.resolved_by == agent

    @pytest.mark.parametrize("decision", ["remove-image", "dismiss"])
    def test_an_agent_cannot_resolve_another_municipality_request(
        self,
        report,
        decision,
    ):
        """CP-043-66. Otra municipalidad no existe para él: ``404``."""
        complaint = ReportComplaintFactory.create(report=report)
        stranger = MunicipalAgentFactory.create()

        response = client_for(stranger).post(f"{INBOX}{complaint.pk}/{decision}/")

        assert response.status_code == HTTP_NOT_FOUND
        complaint.refresh_from_db()
        assert complaint.is_pending
        assert on_disk(report.photo.name)

    def test_a_citizen_gets_403(self, report, neighbour):
        """CP-043-61 (US-043 E10)."""
        response = client_for(neighbour).get(INBOX)

        assert response.status_code == HTTP_FORBIDDEN

    def test_the_municipal_review_queue_never_contains_them(self, report):
        """CP-043-62 (US-043 E10).

        La bandeja de US-021 nace sin este motivo (escenario 10).
        """
        ReportComplaintFactory.create(report=report)

        assert not ReportComplaint.objects.for_municipal_review().exists()
        assert ReportComplaint.objects.for_platform_review().count() == 1


class TestRemovingTheImage:
    """Escenarios 5 y 11."""

    def test_the_file_is_deleted_from_disk(self, admin, report):
        """CP-043-30 (US-043 E5)."""
        name = report.photo.name
        complaint = ReportComplaintFactory.create(report=report)
        assert on_disk(name)

        response = client_for(admin).post(f"{INBOX}{complaint.pk}/remove-image/")

        assert response.status_code == HTTP_OK
        assert not on_disk(name)

    def test_the_report_keeps_everything_else(self, admin, report):
        """CP-043-31 (US-043 E5)."""
        before = Report.objects.get(pk=report.pk)
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        after = Report.objects.get(pk=report.pk)
        assert not after.photo
        assert after.photo_removed_at is not None
        assert after.description == before.description
        assert after.category == before.category
        assert after.latitude == before.latitude
        assert after.longitude == before.longitude
        assert after.status == before.status

    def test_the_whole_report_is_withdrawn_for_good(self, admin, report):
        """CP-043-32 (US-043 E5).

        Un reporte sin foto no se vuelve a publicar (decisión de producto).
        """
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        viewer = client_for(UserFactory.create())
        assert report.pk not in listed_ids(viewer.get("/api/reports/"))
        assert report.pk not in listed_ids(viewer.get("/api/reports/map/"))
        assert viewer.get(f"/api/reports/{report.pk}/").status_code == HTTP_NOT_FOUND
        assert not Report.objects.publicly_visible().filter(pk=report.pk).exists()

    def test_the_author_still_sees_it_as_withdrawn_and_cannot_edit_it(
        self,
        admin,
        report,
    ):
        """CP-043-33 (US-043 E5)."""
        Report.objects.filter(pk=report.pk).update(
            status=Report.Status.PENDIENTE_VALIDACION,
        )
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        detail = client_for(report.author).get(f"/api/reports/{report.pk}/")
        assert detail.status_code == HTTP_OK
        assert detail.data["photo"] is None
        assert detail.data["photo_removed_at"] is not None
        # Una foto nueva no lo volvería a publicar: no se ofrece editarlo.
        assert detail.data["can_edit"] is False

    def test_a_withdrawn_report_does_not_block_reporting_the_problem_again(
        self,
        admin,
        report,
    ):
        """CP-043-34 (US-043 E5)."""
        from urbancheck.reports.duplicates import find_duplicate  # noqa: PLC0415

        Report.objects.filter(pk=report.pk).update(
            status=Report.Status.PENDIENTE_VALIDACION,
        )
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        assert (
            find_duplicate(
                category=report.category,
                latitude=report.latitude,
                longitude=report.longitude,
                municipality=report.municipality,
            )
            is None
        )

    def test_a_withdrawn_report_leaves_the_validator_inbox(self, admin, report):
        """CP-043-35 (US-043 E5)."""
        Report.objects.filter(pk=report.pk).update(
            status=Report.Status.PENDIENTE_VALIDACION,
        )
        complaint = ReportComplaintFactory.create(report=report)
        privacy.remove_image(complaint, admin=admin)
        validator = ValidatorFactory.create(
            municipality=report.municipality,
            must_change_password=False,
        )

        response = client_for(validator).get("/api/validation/reports/")

        assert report.pk not in listed_ids(response)

    def test_the_author_is_notified_with_the_reason(self, admin, report):
        """CP-043-36 (US-043 E5)."""
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        notification = Notification.objects.get(recipient=report.author)
        assert notification.kind == Notification.Kind.IMAGEN_RETIRADA
        assert notification.report == report
        assert "rostro o una patente" in notification.message
        assert notification.actor is None

    def test_every_pending_request_on_that_image_is_closed(self, admin, report):
        """CP-043-37 (US-043 E5)."""
        first = ReportComplaintFactory.create(report=report)
        second = ReportComplaintFactory.create(report=report)

        privacy.remove_image(first, admin=admin)

        second.refresh_from_db()
        assert second.status == ReportComplaint.Status.IMAGEN_ELIMINADA
        assert second.resolved_by == admin

    def test_it_is_registered_with_the_admin_and_the_date(self, admin, report):
        """CP-043-55 (US-043 E8)."""
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        complaint.refresh_from_db()
        assert complaint.status == ReportComplaint.Status.IMAGEN_ELIMINADA
        assert complaint.resolved_by == admin
        assert complaint.resolved_at is not None

    def test_a_resolved_request_cannot_be_decided_again(self, admin, report):
        """CP-043-38 (US-043 E5)."""
        complaint = ReportComplaintFactory.create(report=report)
        privacy.dismiss(complaint, admin=admin)

        response = client_for(admin).post(f"{INBOX}{complaint.pk}/remove-image/")

        assert response.status_code == HTTP_CONFLICT
        assert on_disk(report.photo.name)
        complaint.refresh_from_db()
        assert complaint.status == ReportComplaint.Status.DESESTIMADA

    def test_a_photo_replaced_meanwhile_is_kept_and_the_reported_one_deleted(
        self,
        admin,
        report,
    ):
        """CP-043-39 (US-043 E5).

        Lo que expone el dato es el archivo denunciado, no el de hoy.
        """
        complaint = ReportComplaintFactory.create(report=report)
        reported = complaint.image_name
        report.photo.save("replacement.jpg", ContentFile(b"new"), save=True)

        privacy.remove_image(complaint, admin=admin)

        report.refresh_from_db()
        assert not on_disk(reported)
        assert report.photo
        assert on_disk(report.photo.name)
        assert report.photo_removed_at is None

    def test_an_operator_evidence_photo_is_withdrawn_and_the_status_kept(
        self,
        admin,
        report,
    ):
        """CP-043-66 (US-043 E11).

        Escenario 11.
        """
        Report.objects.filter(pk=report.pk).update(
            status=Report.Status.RESUELTO_PENDIENTE,
        )
        evidence = ResolutionEvidenceFactory.create(report=report)
        name = evidence.photo.name
        complaint = ReportComplaintFactory.create(
            report=report,
            resolution_evidence=evidence,
        )

        privacy.remove_image(complaint, admin=admin)

        evidence.refresh_from_db()
        report.refresh_from_db()
        assert not on_disk(name)
        assert not evidence.photo
        assert evidence.photo_removed_at is not None
        assert evidence.description
        assert report.status == Report.Status.RESUELTO_PENDIENTE
        assert report.photo
        assert on_disk(report.photo.name)
        detail = client_for(UserFactory.create()).get(f"/api/reports/{report.pk}/")
        shown = detail.data["resolution_evidences"][0]
        assert shown["photo"] is None
        assert shown["photo_removed_at"] is not None
        assert shown["description"] == evidence.description

    def test_a_failed_deletion_leaves_the_request_pending(
        self,
        admin,
        report,
        monkeypatch,
    ):
        """CP-043-40 (US-043 E5).

        Si el archivo no se pudo borrar, la base no puede decir que sí.
        """
        complaint = ReportComplaintFactory.create(report=report)

        def broken(name):
            raise OSError(name)

        monkeypatch.setattr(report.photo.storage, "delete", broken)

        with pytest.raises(OSError):  # noqa: PT011
            privacy.remove_image(complaint, admin=admin)

        complaint.refresh_from_db()
        report.refresh_from_db()
        assert complaint.is_pending
        assert report.photo
        assert report.photo_removed_at is None


class TestDismissing:
    """Escenario 6."""

    def test_the_image_stays_and_the_report_is_visible_again(self, admin, report):
        """CP-043-44 (US-043 E6)."""
        complaint = ReportComplaintFactory.create(report=report)

        response = client_for(admin).post(f"{INBOX}{complaint.pk}/dismiss/")

        assert response.status_code == HTTP_OK
        assert on_disk(report.photo.name)
        viewer = client_for(UserFactory.create())
        assert report.pk in listed_ids(viewer.get("/api/reports/"))
        report.refresh_from_db()
        assert report.photo_removed_at is None

    def test_the_decision_is_registered_with_the_admin_and_the_date(
        self,
        admin,
        report,
    ):
        """CP-043-45 (US-043 E6)."""
        complaint = ReportComplaintFactory.create(report=report)

        privacy.dismiss(complaint, admin=admin)

        complaint.refresh_from_db()
        assert complaint.status == ReportComplaint.Status.DESESTIMADA
        assert complaint.resolved_by == admin
        assert complaint.resolved_at is not None



class TestTraceability:
    """Escenario 8: evidencia del cumplimiento del plazo de la RN-12."""

    def test_the_resolved_log_has_every_field(self, admin, report):
        """CP-043-53 (US-043 E8)."""
        complaint = ReportComplaintFactory.create(report=report)
        received(complaint, ago(hours=2))
        privacy.remove_image(complaint, admin=admin)

        response = client_for(admin).get(f"{INBOX}?state=resolved")

        row = response.data["results"][0]
        assert row["id"] == complaint.pk
        assert row["reason"] == ReportComplaint.Reason.DATO_PERSONAL
        assert row["received_at"]
        assert row["resolved_at"]
        assert row["status"] == ReportComplaint.Status.IMAGEN_ELIMINADA
        assert row["resolved_by"]["id"] == admin.pk
        assert row["resolved_within_deadline"] is True
        assert row["remaining_seconds"] is None
        assert row["image"]["url"] is None

    def test_a_late_resolution_is_recorded_as_such(self, admin, report):
        """CP-043-54 (US-043 E8)."""
        complaint = ReportComplaintFactory.create(report=report)
        received(complaint, ago(hours=30))
        privacy.dismiss(complaint, admin=admin)

        row = client_for(admin).get(f"{INBOX}?state=resolved").data["results"][0]

        assert row["resolved_within_deadline"] is False


def kinds_for(user) -> list[str]:
    return list(
        Notification.objects.filter(recipient=user)
        .order_by("created_at")
        .values_list("kind", flat=True),
    )


class TestNotifications:
    """Quién se entera de cada paso del circuito, y quién no."""

    def test_the_author_learns_the_report_was_hidden(self, report, neighbour):
        """CP-043-71 (US-043 Avisos)."""
        request_review(client_for(neighbour), report)

        notification = Notification.objects.get(recipient=report.author)
        assert notification.kind == Notification.Kind.REPORTE_EN_REVISION
        assert notification.report == report
        # Quién denunció no se expone.
        assert notification.actor is None
        assert neighbour.name not in notification.message

    def test_the_author_is_told_once_however_many_neighbours_report_it(
        self,
        report,
        neighbour,
    ):
        """CP-043-72 (US-043 Avisos)."""
        request_review(client_for(neighbour), report)
        request_review(client_for(UserFactory.create()), report)

        assert kinds_for(report.author) == [Notification.Kind.REPORTE_EN_REVISION]

    def test_an_author_reporting_their_own_photo_gets_no_hidden_notice(
        self,
        report,
        author,
    ):
        """CP-043-73 (US-043 Avisos)."""
        request_review(client_for(author), report)

        assert kinds_for(author) == []

    def test_a_dismissal_tells_the_author_it_is_public_again(
        self,
        report,
        neighbour,
        admin,
    ):
        """CP-043-47 (US-043 E6)."""
        complaint = ReportComplaintFactory.create(report=report, reporter=neighbour)

        privacy.dismiss(complaint, admin=admin)

        assert kinds_for(report.author) == [Notification.Kind.REPORTE_RESTITUIDO]

    def test_a_dismissal_tells_every_reporter_the_result(self, report, admin):
        """CP-043-48 (US-043 E6)."""
        first = ReportComplaintFactory.create(report=report)
        second = ReportComplaintFactory.create(report=report)

        privacy.dismiss(first, admin=admin)

        for complaint in (first, second):
            notification = Notification.objects.get(recipient=complaint.reporter)
            assert notification.kind == Notification.Kind.DENUNCIA_RESUELTA
            assert "no muestra datos personales" in notification.message

    def test_a_removal_tells_every_reporter_the_result(self, report, admin):
        """CP-043-42 (US-043 E5)."""
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        notification = Notification.objects.get(recipient=complaint.reporter)
        assert notification.kind == Notification.Kind.DENUNCIA_RESUELTA
        assert "Retiramos el reporte que denunciaste" in notification.message

    def test_an_author_who_reported_gets_only_the_author_notice(
        self,
        report,
        author,
        admin,
    ):
        """CP-043-74 (US-043 Avisos)."""
        complaint = ReportComplaintFactory.create(report=report, reporter=author)

        privacy.dismiss(complaint, admin=admin)

        assert kinds_for(author) == [Notification.Kind.REPORTE_RESTITUIDO]

    def test_no_restored_notice_while_another_image_keeps_it_hidden(
        self,
        report,
        admin,
    ):
        """CP-043-75 (US-043 Avisos)."""
        evidence = ResolutionEvidenceFactory.create(report=report)
        on_photo = ReportComplaintFactory.create(report=report)
        ReportComplaintFactory.create(report=report, resolution_evidence=evidence)

        privacy.dismiss(on_photo, admin=admin)

        assert Notification.Kind.REPORTE_RESTITUIDO not in kinds_for(report.author)

    def test_the_removal_notice_does_not_claim_it_is_public_while_still_hidden(
        self,
        report,
        admin,
    ):
        """CP-043-69 (US-043 E11).

        Se retira la foto de un cierre mientras la del reporte sigue en revisión.
        """
        evidence = ResolutionEvidenceFactory.create(report=report)
        on_evidence = ReportComplaintFactory.create(
            report=report,
            resolution_evidence=evidence,
        )
        ReportComplaintFactory.create(report=report)

        privacy.remove_image(on_evidence, admin=admin)

        notice = Notification.objects.get(
            recipient=report.author,
            kind=Notification.Kind.IMAGEN_RETIRADA,
        )
        assert "sigue oculto" in notice.message
        assert "sigue publicado" not in notice.message

    def test_removing_an_evidence_photo_says_it_is_public_when_it_is(
        self,
        report,
        admin,
    ):
        """CP-043-70 (US-043 E11)."""
        evidence = ResolutionEvidenceFactory.create(report=report)
        complaint = ReportComplaintFactory.create(
            report=report,
            resolution_evidence=evidence,
        )

        privacy.remove_image(complaint, admin=admin)

        notice = Notification.objects.get(recipient=report.author)
        assert "sigue publicado" in notice.message
        assert Report.objects.publicly_visible().filter(pk=report.pk).exists()

    def test_removing_the_report_photo_tells_the_author_it_was_withdrawn(
        self,
        report,
        admin,
    ):
        """CP-043-43 (US-043 E5)."""
        complaint = ReportComplaintFactory.create(report=report)

        privacy.remove_image(complaint, admin=admin)

        notice = Notification.objects.get(recipient=report.author)
        assert "Retiramos tu reporte" in notice.message
        assert "Ya no está publicado" in notice.message
        assert "sigue publicado" not in notice.message

