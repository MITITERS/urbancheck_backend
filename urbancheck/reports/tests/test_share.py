"""US-030 — compartir un reporte con un enlace único."""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.apps import apps as django_apps
from django.utils.html import escapejs
from rest_framework.test import APIClient

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ModerationDecisionFactory
from urbancheck.reports.tests.factories import OfficialResponseFactory
from urbancheck.reports.tests.factories import ReportComplaintFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_NOT_FOUND = 404

Status = Report.Status


def public(report_or_token) -> object:
    token = getattr(report_or_token, "share_token", report_or_token)
    return APIClient().get(f"/api/public/reports/{token}/")


def detail_for(user, report):
    client = APIClient()
    client.force_authenticate(user)
    return client.get(f"/api/reports/{report.pk}/")


class TestTheLink:
    def test_every_report_has_its_own_random_token(self):
        """CP-030-01 (US-030 E1). Único, y no el id correlativo."""
        first, second = ReportFactory.create_batch(2)

        assert first.share_token != second.share_token
        assert first.share_token.version == 4  # noqa: PLR2004 (aleatorio)

    def test_the_detail_offers_the_link(self, settings):
        """CP-030-02 (US-030 E1)."""
        settings.PUBLIC_REPORT_URL = "https://urbancheck.test/r/{token}"
        report = ReportFactory.create(status=Status.REPORTADO)

        data = detail_for(UserFactory.create(), report).data

        assert data["share_url"] == f"https://urbancheck.test/r/{report.share_token}"

    def test_a_report_nobody_else_sees_offers_no_link(self):
        """CP-030-03. El autor ve su reporte cancelado, pero no hay qué compartir."""
        report = ReportFactory.create(status=Status.CANCELADO)

        data = detail_for(report.author, report).data

        assert data["share_url"] is None

    def test_the_migration_gives_each_existing_report_a_different_token(self):
        """CP-030-04. Un ``default`` en ``AddField`` les daría a todos el mismo."""
        reports = ReportFactory.create_batch(3)
        module = importlib.import_module(
            "urbancheck.reports.migrations.0018_report_share_token",
        )
        # La columna ya es NOT NULL acá: se comprueba que la función no pise
        # los tokens que ya existen.
        before = {r.pk: r.share_token for r in reports}

        module.give_every_report_a_token(django_apps, None)

        after = dict(Report.objects.values_list("pk", "share_token"))
        assert after == before
        assert len(set(after.values())) == len(reports)


class TestThePublicPage:
    def test_anyone_without_the_app_sees_the_details(self):
        """CP-030-05 (US-030 E2). Sin sesión."""
        report = ReportFactory.create(
            status=Status.EN_PROCESO,
            description="Bache profundo",
            address="Av. Siempre Viva 742",
        )
        LikeFactory.create(report=report)
        OfficialResponseFactory.create(report=report, text="Ya está asignado.")

        response = public(report)

        assert response.status_code == HTTP_OK
        data = response.data
        assert data["description"] == "Bache profundo"
        assert data["status_label"] == "En proceso"
        assert data["address"] == "Av. Siempre Viva 742"
        assert data["like_count"] == 1
        assert data["photo"]
        assert [r["text"] for r in data["official_responses"]] == ["Ya está asignado."]
        assert data["timeline"]

    def test_it_never_exposes_people(self):
        """CP-030-06. Ni el autor ni quién intervino: responde el municipio."""
        report = ReportFactory.create(status=Status.REPORTADO)

        data = public(report).data

        assert "author" not in data
        assert report.author.email not in str(data)
        assert report.author.name not in str(data)

    @pytest.mark.parametrize("status", [Status.CANCELADO, Status.ARCHIVADO])
    def test_an_archived_or_cancelled_report_is_no_longer_available(self, status):
        """CP-030-07 (US-030 E3)."""
        report = ReportFactory.create(status=status)

        response = public(report)

        assert response.status_code == HTTP_NOT_FOUND
        assert response.data["code"] == "report_unavailable"
        assert response.data["moderation"] is None

    def test_a_deleted_report_is_no_longer_available(self):
        """CP-030-08 (US-030 E3). El enlace sobrevive al reporte: el token no."""
        report = ReportFactory.create()
        token = report.share_token
        report.delete()

        response = public(token)

        assert response.status_code == HTTP_NOT_FOUND
        assert response.data["code"] == "report_unavailable"

    def test_a_report_hidden_for_privacy_is_not_available(self):
        """CP-030-09. La misma función de visibilidad que el feed."""
        report = ReportFactory.create(status=Status.REPORTADO)
        ReportComplaintFactory.create(report=report)  # dato personal, pendiente

        assert public(report).status_code == HTTP_NOT_FOUND

    def test_an_unprocessed_photo_is_not_available(self):
        """CP-030-10 (US-042). Nada se publica antes del difuminado."""
        report = ReportFactory.create(status=Status.REPORTADO)
        Report.objects.filter(pk=report.pk).update(
            photo="",
            photo_status=PhotoStatus.PENDIENTE,
        )

        assert public(report).status_code == HTTP_NOT_FOUND

    def test_a_discarded_report_shows_the_public_reason(self):
        """CP-030-11 (US-049). No disponible, pero con el motivo del descarte."""
        decision = ModerationDecisionFactory.create(reason="No existe")

        response = public(decision.report)

        assert response.status_code == HTTP_NOT_FOUND
        assert response.data["moderation"]["reason"] == "No existe"
        assert response.data["moderation"]["can_appeal"] is False

    def test_an_unknown_token_is_a_404(self):
        """CP-030-12."""
        assert public(uuid.uuid4()).status_code == HTTP_NOT_FOUND

    def test_the_id_does_not_open_it(self):
        """CP-030-13. Solo el token: el id se podría recorrer."""
        report = ReportFactory.create()

        response = APIClient().get(f"/api/public/reports/{report.pk}/")

        assert response.status_code == HTTP_NOT_FOUND


def test_the_app_opens_the_link_when_installed(client):
    """CP-030-14 (US-030 E2). iOS abre ``/r/*`` en la app."""
    data = client.get("/.well-known/apple-app-site-association").json()

    assert "/r/*" in data["applinks"]["details"][0]["paths"]


class TestPreviewInSocialNetworks:
    """La tarjeta del enlace en WhatsApp, Facebook o X: etiquetas Open Graph en
    el HTML del servidor, porque los bots no ejecutan JavaScript."""

    def test_the_link_carries_title_description_and_photo(self, client, settings):
        """CP-030-15. La foto difuminada, con URL absoluta."""
        settings.PUBLIC_REPORT_PAGE_URL = "/reporte/{token}"
        report = ReportFactory.create(
            status=Status.EN_PROCESO,
            description="Bache profundo frente a la escuela",
        )

        response = client.get(f"/r/{report.share_token}")

        assert response.status_code == HTTP_OK
        html = response.content.decode()
        assert '<meta property="og:title" content="Bache en ' in html
        assert "Bache profundo frente a la escuela" in html
        # En los tests ``MEDIA_URL`` ya es absoluta; en producción la arma
        # ``build_absolute_uri`` con el dominio del pedido.
        assert f'<meta property="og:image" content="{report.photo.url}"' in html
        assert 'name="twitter:card" content="summary_large_image"' in html

    def test_a_person_goes_on_to_the_panel_page(self, client, settings):
        """CP-030-16 (US-030 E2). Los bots se quedan; la persona sigue de largo."""
        settings.PUBLIC_REPORT_PAGE_URL = "http://localhost:5173/reporte/{token}"
        report = ReportFactory.create(status=Status.REPORTADO)

        html = client.get(f"/r/{report.share_token}").content.decode()

        target = escapejs(f"http://localhost:5173/reporte/{report.share_token}")
        assert f'window.location.replace("{target}")' in html

    def test_the_text_is_escaped(self, client):
        """CP-030-17. La descripción la escribe el vecino: no puede inyectar HTML."""
        report = ReportFactory.create(
            status=Status.REPORTADO,
            description='"><script>alert(1)</script>',
        )

        html = client.get(f"/r/{report.share_token}").content.decode()

        assert "<script>alert(1)</script>" not in html

    def test_it_never_names_the_author(self, client):
        """CP-030-18."""
        report = ReportFactory.create(status=Status.REPORTADO)

        html = client.get(f"/r/{report.share_token}").content.decode()

        assert report.author.name not in html
        assert report.author.email not in html

    @pytest.mark.parametrize("status", [Status.CANCELADO, Status.ARCHIVADO])
    def test_an_unavailable_report_leaks_nothing(self, client, status):
        """CP-030-19 (US-030 E3). Sin foto ni descripción en la tarjeta."""
        report = ReportFactory.create(status=status, description="Texto privado")

        response = client.get(f"/r/{report.share_token}")

        assert response.status_code == HTTP_NOT_FOUND
        html = response.content.decode()
        assert "ya no está disponible" in html
        assert "Texto privado" not in html
        assert "og:image" not in html
