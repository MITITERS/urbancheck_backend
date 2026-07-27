"""US-018 (editar reporte propio) y US-019 (eliminar reporte propio)."""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

# Estados en los que el municipio ya tomó el reporte: edición y borrado bloqueados.
LOCKED_STATUSES = [
    Report.Status.EN_PROCESO,
    Report.Status.RESUELTO,
    Report.Status.CANCELADO,
    Report.Status.ARCHIVADO,
]


def make_image_file(name="edit.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), color=(10, 20, 30)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestReportUpdate:
    def test_author_can_edit_pending_report(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(
            author=user, status=Report.Status.PENDIENTE_VALIDACION
        )
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"description": "Descripción corregida", "category": "basura"},
            format="json",
        )
        assert res.status_code == 200
        report.refresh_from_db()
        assert report.description == "Descripción corregida"
        assert report.category == Report.Category.BASURA

    def test_author_can_edit_reported_report(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"description": "Otra descripción"},
            format="json",
        )
        assert res.status_code == 200

    def test_edit_records_edited_at(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        assert report.edited_at is None
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"description": "Editado"},
            format="json",
        )
        assert res.status_code == 200
        report.refresh_from_db()
        assert report.edited_at is not None
        assert res.data["edited_at"] is not None

    def test_can_replace_photo(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        original = report.photo.name
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"photo": make_image_file()},
            format="multipart",
        )
        assert res.status_code == 200
        report.refresh_from_db()
        assert report.photo.name != original

    @pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
    def test_cannot_edit_when_in_management(self, auth_client, locked_status):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=locked_status)
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"description": "Intento de edición"},
            format="json",
        )
        assert res.status_code == 403
        report.refresh_from_db()
        assert report.description != "Intento de edición"

    def test_other_user_cannot_edit(self, auth_client):
        client, _ = auth_client
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"description": "No debería poder"},
            format="json",
        )
        assert res.status_code == 403

    def test_empty_description_rejected(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        res = client.patch(
            f"/api/reports/{report.id}/",
            data={"description": "   "},
            format="json",
        )
        assert res.status_code == 400

    def test_detail_exposes_can_edit(self, auth_client):
        client, user = auth_client
        own_editable = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        own_locked = ReportFactory.create(author=user, status=Report.Status.EN_PROCESO)
        someone_else = ReportFactory.create(status=Report.Status.REPORTADO)

        assert client.get(f"/api/reports/{own_editable.id}/").data["can_edit"] is True
        assert client.get(f"/api/reports/{own_locked.id}/").data["can_edit"] is False
        assert client.get(f"/api/reports/{someone_else.id}/").data["can_edit"] is False


@pytest.mark.django_db
class TestReportDelete:
    def test_author_can_delete_reported(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        res = client.delete(f"/api/reports/{report.id}/")
        assert res.status_code == 204
        assert not Report.objects.filter(id=report.id).exists()

    def test_deleted_report_disappears_from_feed_and_map(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=Report.Status.REPORTADO)
        client.delete(f"/api/reports/{report.id}/")

        feed = client.get("/api/reports/")
        assert report.id not in {r["id"] for r in feed.data["results"]}

        mapa = client.get("/api/reports/map/")
        assert report.id not in {r["id"] for r in mapa.data["results"]}

    @pytest.mark.parametrize("locked_status", LOCKED_STATUSES)
    def test_cannot_delete_when_in_management(self, auth_client, locked_status):
        client, user = auth_client
        report = ReportFactory.create(author=user, status=locked_status)
        res = client.delete(f"/api/reports/{report.id}/")
        assert res.status_code == 403
        assert Report.objects.filter(id=report.id).exists()

    def test_other_user_cannot_delete(self, auth_client):
        client, _ = auth_client
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        res = client.delete(f"/api/reports/{report.id}/")
        assert res.status_code == 403
        assert Report.objects.filter(id=report.id).exists()
