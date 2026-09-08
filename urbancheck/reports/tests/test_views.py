from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


def make_image_file(name="test.jpg"):
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestReportCreate:
    def test_create_success(self, auth_client):
        client, user = auth_client
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Hay un bache enorme",
                "category": "bache",
                "latitude": "-34.6",
                "longitude": "-58.4",
            },
            format="multipart",
        )
        assert res.status_code == 201
        report = Report.objects.get(id=res.data["id"])
        assert report.author == user
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    def test_create_adds_initial_status_history(self, auth_client):
        client, _ = auth_client
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Test reporte",
                "category": "bache",
                "address": "Av. Corrientes 1234",
            },
            format="multipart",
        )
        assert res.status_code == 201
        assert ReportStatusHistory.objects.filter(
            report_id=res.data["id"], status="pendiente_validacion"
        ).exists()

    def test_create_without_photo_returns_400(self, auth_client):
        client, _ = auth_client
        res = client.post(
            "/api/reports/",
            data={
                "description": "Sin foto",
                "category": "bache",
                "address": "Alguna dirección",
            },
            format="multipart",
        )
        assert res.status_code == 400

    def test_create_without_location_returns_400(self, auth_client):
        client, _ = auth_client
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Sin ubicación",
                "category": "bache",
            },
            format="multipart",
        )
        assert res.status_code == 400

    def test_create_anonymous_returns_401_or_403(self, db):
        client = APIClient()
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Anónimo",
                "category": "bache",
                "address": "Dirección cualquiera",
            },
            format="multipart",
        )
        assert res.status_code in (401, 403)


@pytest.mark.django_db
class TestReportList:
    def test_list_returns_reports(self, auth_client):
        client, _ = auth_client
        ReportFactory.create_batch(3)
        res = client.get("/api/reports/")
        assert res.status_code == 200
        assert res.data["count"] >= 3

    def test_mine_filter(self, auth_client):
        client, user = auth_client
        ReportFactory.create(author=user)
        ReportFactory.create()  # another user's report
        res = client.get("/api/reports/?mine=true")
        assert res.status_code == 200
        for r in res.data["results"]:
            assert r["author"]["id"] == user.id


@pytest.mark.django_db
class TestReportDetail:
    def test_detail_includes_status_history(self, auth_client):
        client, _ = auth_client
        report = ReportFactory.create()
        ReportStatusHistory.objects.create(
            report=report, status="reportado", changed_by=report.author
        )
        res = client.get(f"/api/reports/{report.id}/")
        assert res.status_code == 200
        assert len(res.data["status_history"]) >= 1

    def test_detail_is_liked_false_by_default(self, auth_client):
        client, _ = auth_client
        report = ReportFactory.create()
        res = client.get(f"/api/reports/{report.id}/")
        assert res.data["is_liked"] is False


@pytest.mark.django_db
class TestLike:
    def test_like_report(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        res = client.post(f"/api/reports/{report.id}/like/")
        assert res.status_code == 201
        assert Like.objects.filter(report=report, user=user).exists()
        assert res.data == {"liked": True, "like_count": 1}

    def test_unlike_report(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        LikeFactory.create(report=report, user=user)
        res = client.delete(f"/api/reports/{report.id}/like/")
        assert res.status_code == 200
        assert not Like.objects.filter(report=report, user=user).exists()
        assert res.data == {"liked": False, "like_count": 0}

    def test_like_idempotent(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        client.post(f"/api/reports/{report.id}/like/")
        client.post(f"/api/reports/{report.id}/like/")
        assert Like.objects.filter(report=report, user=user).count() == 1

    def test_like_count_reflects_other_users(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        LikeFactory.create(report=report)  # like de otro usuario
        res = client.post(f"/api/reports/{report.id}/like/")
        assert res.data["like_count"] == 2

    def test_is_liked_present_without_annotation(self, auth_client):
        """El campo no debe desaparecer si el queryset no anota ``is_liked``.

        Un campo declarativo de solo lectura se omite en silencio cuando falta el
        atributo, y el cliente se quedaría sin el estado del botón de like.
        """
        from rest_framework.test import APIRequestFactory

        from urbancheck.reports.api.serializers import ReportDetailSerializer

        _, user = auth_client
        report = ReportFactory.create()
        LikeFactory.create(report=report, user=user)

        request = APIRequestFactory().get(f"/api/reports/{report.id}/")
        request.user = user
        data = ReportDetailSerializer(report, context={"request": request}).data
        assert data["is_liked"] is True

    def test_feed_exposes_is_liked(self, auth_client):
        client, user = auth_client
        liked = ReportFactory.create()
        LikeFactory.create(report=liked, user=user)
        not_liked = ReportFactory.create()
        res = client.get("/api/reports/")
        by_id = {r["id"]: r for r in res.data["results"]}
        assert by_id[liked.id]["is_liked"] is True
        assert by_id[not_liked.id]["is_liked"] is False


@pytest.mark.django_db
class TestComments:
    def test_add_comment(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        res = client.post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Buen reporte"},
            format="json",
        )
        assert res.status_code == 201
        assert res.data["author"]["id"] == user.id

    def test_list_comments(self, auth_client):
        client, _ = auth_client
        report = ReportFactory.create()
        CommentFactory.create_batch(3, report=report)
        res = client.get(f"/api/reports/{report.id}/comments/")
        assert res.status_code == 200
        assert len(res.data) >= 3

    def test_anonymous_comment_returns_401_or_403(self, db):
        report = ReportFactory.create()
        client = APIClient()
        res = client.post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Hola"},
            format="json",
        )
        assert res.status_code in (401, 403)


@pytest.mark.django_db
class TestGpsPrecision:
    """El GPS del teléfono manda más decimales de los que guardamos.

    Antes esto rechazaba el reporte con «no puede haber más de 9 dígitos en
    total», un error incomprensible sobre un dato que el vecino no escribió.
    """

    def test_a_real_gps_reading_is_accepted_and_rounded(self):
        author = UserFactory.create()
        client = APIClient()
        client.force_authenticate(author)

        response = client.post(
            "/api/reports/",
            {
                "description": "Bache con GPS de alta precisión",
                "category": Report.Category.BACHE,
                "latitude": "-32.4103142822017",
                "longitude": "-63.2400933841481",
                "photo": make_image_file(),
            },
            format="multipart",
        )

        assert response.status_code == 201
        report = Report.objects.get(pk=response.data["id"])
        assert str(report.latitude) == "-32.410314"
        assert str(report.longitude) == "-63.240093"

    def test_a_coordinate_off_the_planet_is_still_rejected(self):
        client = APIClient()
        client.force_authenticate(UserFactory.create())

        response = client.post(
            "/api/reports/",
            {
                "description": "Bache en Marte",
                "category": Report.Category.BACHE,
                "latitude": "120.0",
                "longitude": "-63.24",
                "photo": make_image_file(),
            },
            format="multipart",
        )

        assert response.status_code == 400
        assert "latitude" in response.data
