"""US-043 — la foto de una apelación, el panel y la bandeja del admin de Django.

Completa lo que ``test_privacy_requests.py`` no cubría:

- el escenario 1 nombra tres imágenes denunciables —la del reporte, la de un
  cierre y la de una apelación— y la tercera no se podía denunciar;
- el agente sigue viendo un reporte retenido, pero no la imagen denunciada;
- el administrador también resuelve desde el admin de Django (punto 4 de las
  instrucciones del Sprint 5), con los mismos servicios que el panel.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.reports.admin import ReportComplaintAdmin
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.privacy import remove_image
from urbancheck.reports.tests.factories import ReportComplaintFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionAppealFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def on_disk(name: str) -> bool:
    return bool(name) and (Path(settings.MEDIA_ROOT) / name).is_file()


@pytest.fixture
def report(active_municipality):
    return ReportFactory.create(
        municipality=active_municipality,
        status=Report.Status.EN_PROCESO,
    )


@pytest.fixture
def appeal(report):
    return ResolutionAppealFactory.create(report=report)


class TestTheAppealPhoto:
    def test_anyone_can_ask_to_review_it(self, report, appeal):
        """CP-043-10 (US-043 E1).

        se denuncia la foto de una apelación y el reporte se oculta.
        """
        response = client_for(UserFactory.create()).post(
            f"/api/reports/{report.pk}/privacy-request/",
            {"appeal": appeal.pk},
            format="json",
        )

        assert response.status_code == 201  # noqa: PLR2004
        assert response.data["appeal"] == appeal.pk
        complaint = ReportComplaint.objects.get(pk=response.data["id"])
        assert complaint.image_kind == "resolution_appeal"
        assert complaint.image_name == appeal.photo.name
        assert not Report.objects.publicly_visible().filter(pk=report.pk).exists()

    def test_an_appeal_of_another_report_is_rejected(self, report):
        """CP-043-11 (US-043 E1).

        la imagen tiene que pertenecer al reporte de la URL.
        """
        foreign = ResolutionAppealFactory.create()

        response = client_for(UserFactory.create()).post(
            f"/api/reports/{report.pk}/privacy-request/",
            {"appeal": foreign.pk},
            format="json",
        )

        assert response.status_code == 400  # noqa: PLR2004
        assert "appeal" in response.data

    def test_one_image_per_request(self, report, appeal):
        """CP-043-12 (US-043 E1).

        no se denuncian dos imágenes en la misma solicitud.
        """
        response = client_for(UserFactory.create()).post(
            f"/api/reports/{report.pk}/privacy-request/",
            {"appeal": appeal.pk, "evidence": 1},
            format="json",
        )

        assert response.status_code == 400  # noqa: PLR2004

    def test_removing_it_keeps_the_report_and_the_appeal(
        self,
        report,
        appeal,
    ):
        """CP-043-67 (US-043 E11).

        se borra la foto; el reporte y el motivo de la objeción quedan.
        """
        complaint = ReportComplaintFactory.create(
            report=report,
            resolution_appeal=appeal,
            image_name=appeal.photo.name,
        )
        name = appeal.photo.name

        remove_image(complaint, admin=PlatformAdminFactory.create())

        appeal.refresh_from_db()
        report.refresh_from_db()
        assert not on_disk(name)
        assert not appeal.photo
        assert appeal.photo_removed_at is not None
        assert appeal.reason
        assert report.photo
        assert report.photo_removed_at is None
        assert Report.objects.publicly_visible().filter(pk=report.pk).exists()
        notice = Notification.objects.get(
            recipient=report.author,
            kind=Notification.Kind.IMAGEN_RETIRADA,
        )
        assert "objeción" in notice.message

    def test_the_citizen_payload_says_the_photo_was_withdrawn(self, report, appeal):
        """CP-043-68 (US-043 E11).

        la app sabe que la foto de la objeción se retiró.
        """
        complaint = ReportComplaintFactory.create(
            report=report,
            resolution_appeal=appeal,
            image_name=appeal.photo.name,
        )
        remove_image(complaint, admin=PlatformAdminFactory.create())

        data = client_for(report.author).get(f"/api/reports/{report.pk}/").data

        [row] = data["resolution_appeals"]
        assert row["photo"] is None
        assert row["photo_removed_at"] is not None


class TestThePanelShowsTheImageUnderReview:
    """Pedido del usuario del 21/10: el agente y el admin ven siempre la imagen
    denunciada, sea cual sea el motivo, porque la resuelven."""

    def test_the_report_photo_is_shown_while_under_review(self, report):
        """CP-VIS-02: el agente ve el reporte retenido, con la foto denunciada."""
        ReportComplaintFactory.create(report=report)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        data = client_for(agent).get(f"/api/panel/reports/{report.pk}/").data

        assert data["under_privacy_review"] is True
        assert data["photo"]

    def test_the_reported_appeal_photo_is_shown_too(self, report, appeal):
        """CP-VIS-03: también la de una objeción denunciada."""
        ReportComplaintFactory.create(
            report=report,
            resolution_appeal=appeal,
            image_name=appeal.photo.name,
        )
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        data = client_for(agent).get(f"/api/panel/reports/{report.pk}/").data

        assert data["photo"]
        [row] = data["resolution_appeals"]
        assert row["photo"]

    def test_once_dismissed_the_photo_is_back(self, report):
        """CP-VIS-04: desestimada la solicitud, el panel vuelve a mostrarla."""
        ReportComplaintFactory.create(
            report=report,
            status=ReportComplaint.Status.DESESTIMADA,
        )
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        data = client_for(agent).get(f"/api/panel/reports/{report.pk}/").data

        assert data["photo"]


def admin_request(user):
    request = RequestFactory().post("/admin/reports/reportcomplaint/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)  # noqa: SLF001
    return request


@pytest.fixture
def model_admin():
    return ReportComplaintAdmin(ReportComplaint, AdminSite())


class TestTheDjangoAdminInbox:
    def test_removing_from_the_admin_goes_through_the_service(
        self,
        model_admin,
        report,
    ):
        """CP-043-41 (US-043 E5).

        la acción del admin borra el archivo y retira el reporte.
        """
        complaint = ReportComplaintFactory.create(report=report)
        name = report.photo.name
        admin = PlatformAdminFactory.create(is_staff=True)

        model_admin.remove_selected_images(
            admin_request(admin),
            ReportComplaint.objects.filter(pk=complaint.pk),
        )

        complaint.refresh_from_db()
        assert complaint.status == ReportComplaint.Status.IMAGEN_ELIMINADA
        assert complaint.resolved_by == admin
        assert not on_disk(name)

    def test_dismissing_from_the_admin_restores_the_report(self, model_admin, report):
        """CP-043-46 (US-043 E6).

        la acción de desestimar devuelve la visibilidad.
        """
        complaint = ReportComplaintFactory.create(report=report)
        admin = PlatformAdminFactory.create(is_staff=True)

        model_admin.dismiss_selected_requests(
            admin_request(admin),
            ReportComplaint.objects.filter(pk=complaint.pk),
        )

        complaint.refresh_from_db()
        assert complaint.status == ReportComplaint.Status.DESESTIMADA
        assert Report.objects.publicly_visible().filter(pk=report.pk).exists()

    def test_content_complaints_are_not_touched(self, model_admin, report):
        """CP-043-65 (US-043 E10).

        las de contenido son del agente (US-049), no se resuelven acá.
        """
        complaint = ReportComplaintFactory.create(
            report=report,
            reason=ReportComplaint.Reason.REPORTE_FALSO,
        )

        model_admin.remove_selected_images(
            admin_request(PlatformAdminFactory.create(is_staff=True)),
            ReportComplaint.objects.filter(pk=complaint.pk),
        )

        complaint.refresh_from_db()
        assert complaint.is_pending

    def test_only_the_platform_admin_can_resolve(self, model_admin):
        """CP-043-64 (US-043 E10).

        un agente con acceso al admin no ve las acciones.
        """
        agent = MunicipalAgentFactory.create(is_staff=True)

        assert not model_admin.has_resolve_permission(admin_request(agent))
        assert model_admin.has_resolve_permission(
            admin_request(PlatformAdminFactory.create(is_staff=True)),
        )

    def test_the_inbox_flags_overdue_requests(self, model_admin, report, settings):
        """CP-043-52 (US-043 E7).

        la columna "fuera de plazo" del admin.
        """
        complaint = ReportComplaintFactory.create(report=report)
        settings.PERSONAL_DATA_REVIEW_MINUTES = 0

        assert model_admin.overdue(complaint) is True
