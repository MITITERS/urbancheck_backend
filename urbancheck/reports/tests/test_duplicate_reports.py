"""US-032 — impedir la creación de un reporte que ya existe."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.anonymization.storage import pending_photo_storage
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import square_boundary
from urbancheck.reports.api import views
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_CONFLICT = 409

HERE = (-32.410300, -63.240000)
#: ~11 m al norte de ``HERE``: dentro del radio de 30 m.
NEARBY = (-32.410200, -63.240000)
#: ~111 m al norte de ``HERE``: fuera del radio.
FAR = (-32.409300, -63.240000)


def make_image_file():
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color=(100, 100, 100)).save(buf, format="JPEG")
    return SimpleUploadedFile("foto.jpg", buf.getvalue(), content_type="image/jpeg")


def media_files() -> set[Path]:
    return {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}


def pending_files() -> set[Path]:
    """Las originales a la espera del difuminado (US-042)."""
    root = Path(pending_photo_storage().location)
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_file()}


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def create_report(client, point=NEARBY, category="bache", **extra):
    latitude, longitude = point
    return client.post(
        "/api/reports/",
        {
            "photo": make_image_file(),
            "description": "Bache frente a la escuela.",
            "category": category,
            "latitude": str(latitude),
            "longitude": str(longitude),
            **extra,
        },
        format="multipart",
    )


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def existing(active_municipality, author):
    return ReportFactory.create(
        author=author,
        municipality=active_municipality,
        category=Report.Category.BACHE,
        status=Report.Status.PENDIENTE_VALIDACION,
        latitude=HERE[0],
        longitude=HERE[1],
    )


@pytest.fixture
def neighbour():
    return UserFactory.create()


@pytest.fixture
def neighbour_client(neighbour):
    return client_for(neighbour)


class TestBlocked:
    """Escenarios 1 y 8: el reporte no se crea y la respuesta es identificable."""

    def test_it_answers_409_with_its_own_code(self, existing, neighbour_client):
        response = create_report(neighbour_client)

        assert response.status_code == HTTP_CONFLICT
        assert response.data["code"] == "report_already_exists"
        assert "duplicado" not in response.data["detail"].lower()

    def test_it_carries_the_existing_report(self, existing, neighbour_client):
        response = create_report(neighbour_client)

        report = response.data["existing_report"]
        assert report["id"] == existing.id
        assert report["photo"]
        assert report["category"] == "bache"
        assert report["status"] == "pendiente_validacion"
        assert report["created_at"]
        assert report["like_count"] == 0
        assert report["is_liked"] is False
        assert report["is_author"] is False
        # ~11 m, redondeado a metros.
        assert 5 <= report["distance_meters"] <= 20  # noqa: PLR2004

    def test_the_closest_one_wins(
        self,
        existing,
        active_municipality,
        neighbour_client,
    ):
        closer = ReportFactory.create(
            municipality=active_municipality,
            category=Report.Category.BACHE,
            status=Report.Status.REPORTADO,
            latitude=NEARBY[0],
            longitude=NEARBY[1],
        )

        response = create_report(neighbour_client)

        assert response.data["existing_report"]["id"] == closer.id

    def test_an_address_is_geocoded_before_looking(
        self,
        existing,
        neighbour_client,
        monkeypatch,
    ):
        monkeypatch.setattr(
            views,
            "geocode_one",
            lambda address: {"latitude": NEARBY[0], "longitude": NEARBY[1]},
        )

        response = neighbour_client.post(
            "/api/reports/",
            {
                "photo": make_image_file(),
                "description": "Bache.",
                "category": "bache",
                "address": "Bv. España 100",
            },
            format="multipart",
        )

        assert response.status_code == HTTP_CONFLICT

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
            Report.Status.EN_PROCESO,
            Report.Status.RESUELTO_PENDIENTE,
        ],
    )
    def test_every_open_status_blocks(self, existing, neighbour_client, status):
        existing.status = status
        existing.save(update_fields=["status"])

        assert create_report(neighbour_client).status_code == HTTP_CONFLICT

    def test_the_radius_is_read_from_configuration(
        self,
        existing,
        neighbour_client,
        settings,
    ):
        settings.DUPLICATE_REPORT_RADIUS_METERS = 200

        assert create_report(neighbour_client, point=FAR).status_code == HTTP_CONFLICT


class TestNothingIsStored:
    """Escenario 7: ni reporte, ni imagen, ni paso por la anonimización."""

    def test_no_report_and_no_file(self, existing, neighbour_client):
        before = media_files()
        count = Report.objects.count()

        response = create_report(neighbour_client)

        assert response.status_code == HTTP_CONFLICT
        assert Report.objects.count() == count
        assert media_files() == before

    def test_the_photo_never_enters_the_queue(
        self,
        existing,
        neighbour_client,
    ):
        """La foto de un reporte bloqueado no llega ni a guardarse.

        La verificación de duplicado corre antes de validar la foto, así que
        un reporte que no se va a crear no deja nada en el storage privado ni
        encola ningún difuminado (US-042).
        """
        assert create_report(neighbour_client).status_code == HTTP_CONFLICT
        assert pending_files() == set()


class TestJoining:
    """Escenario 2: sumarse es el me gusta de siempre y cuenta para US-040."""

    def test_the_like_counts_toward_collective_validation(
        self,
        existing,
        neighbour_client,
        settings,
    ):
        settings.COLLECTIVE_VALIDATION_THRESHOLD = 1
        blocked = create_report(neighbour_client)
        report_id = blocked.data["existing_report"]["id"]

        response = neighbour_client.post(f"/api/reports/{report_id}/like/")

        assert response.status_code == HTTP_CREATED
        assert response.data["liked"] is True
        existing.refresh_from_db()
        assert existing.confirmation_count() == 1
        assert existing.status == Report.Status.REPORTADO


class TestWhoIsAsking:
    def test_someone_who_already_supports_it(
        self,
        existing,
        neighbour,
        neighbour_client,
    ):
        """Escenario 4: la respuesta dice que ya lo apoya."""
        LikeFactory.create(report=existing, user=neighbour)

        report = create_report(neighbour_client).data["existing_report"]

        assert report["is_liked"] is True
        assert report["like_count"] == 1

    def test_the_author(self, existing, author):
        """Escenario 5: su propio reclamo, marcado como tal."""
        response = create_report(client_for(author))

        assert response.status_code == HTTP_CONFLICT
        assert response.data["existing_report"]["is_author"] is True


class TestNotADuplicate:
    """Escenario 6: sin coincidencia, el reporte se crea como siempre."""

    def test_outside_the_radius(self, existing, neighbour_client):
        assert create_report(neighbour_client, point=FAR).status_code == HTTP_CREATED

    def test_another_category(self, existing, neighbour_client):
        response = create_report(neighbour_client, category="alumbrado")

        assert response.status_code == HTTP_CREATED

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.RESUELTO,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
        ],
    )
    def test_a_closed_report(self, existing, neighbour_client, status):
        existing.status = status
        existing.save(update_fields=["status"])

        assert create_report(neighbour_client).status_code == HTTP_CREATED

    def test_another_municipality(self, existing, neighbour_client):
        existing.municipality = MunicipalityFactory.create(
            boundary=square_boundary(10, 10, 1),
        )
        existing.save(update_fields=["municipality"])

        assert create_report(neighbour_client).status_code == HTTP_CREATED

    def test_the_created_report_enters_the_queue_as_usual(
        self,
        neighbour_client,
    ):
        """Un reporte que sí se crea entra al circuito de difuminado (US-042)."""
        assert create_report(neighbour_client).status_code == HTTP_CREATED

        report = Report.objects.latest("created_at")
        assert report.photo_is_processing
        assert report.photo_pending
        assert len(pending_files()) == 1

    def test_invalid_data_still_gets_every_error(self, neighbour_client):
        response = neighbour_client.post(
            "/api/reports/",
            {"description": "Sin foto ni categoría.", "address": "Bv. España 100"},
            format="multipart",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert {"photo", "category"} <= set(response.data)


class TestForcedClient:
    """Escenario 9: nada que mande el cliente saltea la verificación."""

    def test_a_forcing_flag_is_ignored(self, existing, neighbour_client):
        response = create_report(neighbour_client, force="true", ignore_duplicates="1")

        assert response.status_code == HTTP_CONFLICT
        assert Report.objects.count() == 1
