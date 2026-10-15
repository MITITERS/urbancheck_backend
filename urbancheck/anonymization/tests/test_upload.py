"""US-041 — la foto que se guarda es la anonimizada: escenarios 6 y 7.

Las cuatro puertas por las que una foto entra por la API: crear un reporte,
reemplazar su foto, cerrarlo en terreno (US-046) y apelar el cierre (US-048).
En cada una se sube una foto con el GPS, el modelo del teléfono y un bloque XMP
conocidos, y se verifica que el archivo guardado no conserva nada de eso
(Sprint 5, punto 5.2: SEC-06, SEC-07 y SEC-08).

Con US-042 el difuminado dejó de pasar dentro del request, así que cada caso
tiene ahora dos momentos: el endpoint contesta con la foto todavía en cola, y
la tarea la publica después. Lo que estos tests siguen afirmando es lo mismo de
siempre —lo único que llega a ``MEDIA_ROOT`` es la versión difuminada— más lo
que US-042 agrega: la original vive aparte, en un storage que no se sirve, y
desaparece al terminar.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework import serializers
from rest_framework.test import APIClient

from urbancheck.anonymization import service
from urbancheck.anonymization.service import anonymize
from urbancheck.anonymization.storage import pending_photo_storage
from urbancheck.anonymization.tests.images import assert_no_metadata
from urbancheck.anonymization.tests.images import synthetic_photo
from urbancheck.common.fields import PendingPhotoField
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.admin import ReportAdmin
from urbancheck.reports.api import panel_serializers as report_panel_serializers
from urbancheck.reports.api import serializers as report_serializers
from urbancheck.reports.models import Report
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400

HERE = {"latitude": "-32.410300", "longitude": "-63.240000"}

#: Reporte (alta y edición), cierre y apelación.
WRITABLE_PHOTOS = 4

#: La foto como sale de un celular: con GPS, modelo, fecha y XMP.
SENSITIVE = "foto-del-celular.jpg"


@pytest.fixture(scope="module")
def sensitive_bytes() -> bytes:
    return synthetic_photo()


@pytest.fixture(scope="module")
def expected_bytes(sensitive_bytes) -> bytes:
    """Lo que produce el servicio: lo único que puede quedar guardado."""
    file = io.BytesIO(sensitive_bytes)
    file.name = SENSITIVE
    return anonymize(file).read()


@pytest.fixture
def upload(sensitive_bytes):
    def make() -> SimpleUploadedFile:
        return SimpleUploadedFile(SENSITIVE, sensitive_bytes, content_type="image/jpeg")

    return make


def media_files() -> set[Path]:
    """Lo publicado: todo lo que cae bajo la ruta que se sirve en `/media/`."""
    return {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}


def pending_files() -> set[Path]:
    """Lo que está a la espera, en el storage privado que no se sirve."""
    root = Path(pending_photo_storage().location)
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def author_client(author) -> APIClient:
    client = APIClient()
    client.force_authenticate(author)
    return client


@pytest.fixture
def area(active_municipality):
    return OperationalAreaFactory.create(municipality=active_municipality)


@pytest.fixture
def operator_client(area) -> APIClient:
    client = APIClient()
    client.force_authenticate(OperatorFactory.create(operational_area=area))
    return client


@pytest.fixture
def in_progress(area, author):
    return ReportFactory.create(
        author=author,
        municipality=area.municipality,
        operational_area=area,
        status=Report.Status.EN_PROCESO,
        latitude=HERE["latitude"],
        longitude=HERE["longitude"],
        area_assigned_at=timezone.now(),
    )


def create_report(client, photo):
    return client.post(
        "/api/reports/",
        {
            "photo": photo,
            "description": "Bache frente a la escuela.",
            "category": "bache",
            **HERE,
        },
        format="multipart",
    )


class TestOnlyTheAnonymizedVersionIsStored:
    """Escenario 6: en disco y en la base queda únicamente la versión procesada."""

    def test_creating_a_report(
        self,
        author_client,
        upload,
        sensitive_bytes,
        expected_bytes,
        process_pending_photos,
    ):
        before = media_files()

        response = create_report(author_client, upload())

        assert response.status_code == HTTP_CREATED
        report = Report.objects.get(pk=response.data["id"])
        # Mientras está en cola no hay **nada** publicado: la original espera
        # en el storage privado, que no se sirve por ninguna ruta.
        assert not report.photo
        assert media_files() == before
        assert len(pending_files()) == 1

        process_pending_photos()

        report.refresh_from_db()
        stored = Path(report.photo.path)
        assert media_files() - before == {stored}
        assert stored.read_bytes() == expected_bytes
        assert stored.read_bytes() != sensitive_bytes
        # CP-SEC06-01: la foto del reporte se guarda sin GPS ni metadatos.
        assert_no_metadata(stored.read_bytes())
        # Y la original no sobrevive al procesamiento.
        assert pending_files() == set()

    def test_replacing_the_photo(
        self,
        author_client,
        author,
        upload,
        expected_bytes,
        process_pending_photos,
    ):
        report = ReportFactory.create(
            author=author,
            status=Report.Status.PENDIENTE_VALIDACION,
        )
        before = media_files()

        response = author_client.patch(
            f"/api/reports/{report.pk}/",
            {"photo": upload()},
            format="multipart",
        )

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        # La foto anterior se retira al reemplazarla, así que el reporte queda
        # sin imagen publicada hasta que la nueva termine.
        assert not report.photo
        process_pending_photos()

        report.refresh_from_db()
        assert media_files() - before == {Path(report.photo.path)}
        assert Path(report.photo.path).read_bytes() == expected_bytes
        # CP-SEC06-02: también la foto de reemplazo (US-018).
        assert_no_metadata(Path(report.photo.path).read_bytes())
        assert pending_files() == set()

    def test_the_operator_closing(
        self,
        operator_client,
        in_progress,
        upload,
        expected_bytes,
        process_pending_photos,
    ):
        before = media_files()

        response = operator_client.post(
            f"/api/operator/reports/{in_progress.pk}/resolve/",
            {"photo": upload(), "description": "Se rellenó el bache.", **HERE},
            format="multipart",
        )

        assert response.status_code == HTTP_OK
        evidence = ResolutionEvidence.objects.get(report=in_progress)
        assert not evidence.photo
        process_pending_photos()

        evidence.refresh_from_db()
        assert media_files() - before == {Path(evidence.photo.path)}
        assert Path(evidence.photo.path).read_bytes() == expected_bytes
        # CP-SEC07-01: la evidencia del operario se guarda sin GPS ni metadatos.
        assert_no_metadata(Path(evidence.photo.path).read_bytes())
        assert pending_files() == set()

    def test_the_citizen_appealing(  # noqa: PLR0913 (cada fixture es un actor)
        self,
        operator_client,
        author_client,
        in_progress,
        upload,
        expected_bytes,
        process_pending_photos,
    ):
        operator_client.post(
            f"/api/operator/reports/{in_progress.pk}/resolve/",
            {"photo": upload(), "description": "Se rellenó el bache.", **HERE},
            format="multipart",
        )
        process_pending_photos()
        before = media_files()

        response = author_client.post(
            f"/api/reports/{in_progress.pk}/appeal/",
            {"photo": upload(), "reason": "El bache sigue igual."},
            format="multipart",
        )

        assert response.status_code == HTTP_OK
        appeal = ResolutionAppeal.objects.get(report=in_progress)
        assert not appeal.photo
        process_pending_photos()

        appeal.refresh_from_db()
        assert media_files() - before == {Path(appeal.photo.path)}
        assert Path(appeal.photo.path).read_bytes() == expected_bytes
        # CP-SEC08-01: la foto de la apelación se guarda sin GPS ni metadatos.
        assert_no_metadata(Path(appeal.photo.path).read_bytes())
        assert pending_files() == set()

    def test_a_large_photo_never_touches_a_temporary_file(
        self,
        author_client,
        monkeypatch,
    ):
        """Django pasa a un temporal en disco todo archivo de más de 2,5 MB."""
        rng = np.random.default_rng(7)
        noise = rng.integers(0, 256, size=(1100, 1100, 3), dtype=np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(noise).save(buffer, format="PNG")
        assert buffer.tell() > 2.5 * 1024 * 1024

        def no_temporary_files(*args, **kwargs):
            msg = "La foto original se escribió en un temporal a disco."
            raise AssertionError(msg)

        monkeypatch.setattr(
            "django.core.files.uploadedfile.tempfile.NamedTemporaryFile",
            no_temporary_files,
        )

        response = create_report(
            author_client,
            SimpleUploadedFile(
                "grande.png",
                buffer.getvalue(),
                content_type="image/png",
            ),
        )

        assert response.status_code == HTTP_CREATED

    def test_nothing_is_stored_if_anonymization_fails(
        self,
        author_client,
        upload,
        monkeypatch,
        process_pending_photos,
    ):
        """Si el servicio falla, la foto no se publica sin difuminar.

        Lo que cambió con US-042 es el momento y la respuesta: el alta devuelve
        201 porque el reporte sí se crea, y el fallo llega después. Lo que no
        cambió es lo único que importa: en `MEDIA_ROOT` no queda nada, y la
        original tampoco sobrevive.
        """

        class BrokenDetector:
            def detect(self, bgr):
                msg = "onnxruntime error"
                raise RuntimeError(msg)

        monkeypatch.setattr(service, "_face_detector", BrokenDetector)
        before = media_files()

        response = create_report(author_client, upload())
        assert response.status_code == HTTP_CREATED
        process_pending_photos()

        report = Report.objects.get(pk=response.data["id"])
        assert report.photo_has_failed
        assert not report.photo
        assert media_files() == before
        assert pending_files() == set()


class TestUploadSize:
    def test_a_photo_over_the_limit_is_rejected(self, author_client, upload, settings):
        settings.PHOTO_MAX_UPLOAD_BYTES = 1024

        response = create_report(author_client, upload())

        assert response.status_code == HTTP_BAD_REQUEST
        assert "photo" in response.data

    def test_a_body_over_the_limit_is_rejected_before_reading_it(
        self,
        author_client,
        upload,
        settings,
    ):
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 1024

        response = create_report(author_client, upload())

        assert response.status_code == HTTP_BAD_REQUEST
        assert not Report.objects.exists()


class TestNoWayToTheOriginal:
    """Escenario 7: ningún endpoint, parámetro ni ruta devuelve la original."""

    def test_the_api_serves_the_stored_version(
        self,
        author_client,
        upload,
        process_pending_photos,
    ):
        report_id = create_report(author_client, upload()).data["id"]
        process_pending_photos()
        report = Report.objects.get(pk=report_id)

        detail = author_client.get(f"/api/reports/{report_id}/").data
        feed = author_client.get("/api/reports/").data["results"]

        name = Path(str(report.photo.name)).name
        assert detail["photo"].endswith(name)
        assert next(row for row in feed if row["id"] == report_id)["photo"].endswith(
            name,
        )

    def test_every_photo_the_api_accepts_goes_through_the_queue(self):
        """Una foto nueva que entre por la API tiene que pasar por el servicio.

        Los serializers de entrada se llaman ``*Create*`` o ``*Update*``; los de
        lectura (feed, mapa, detalle) nunca reciben datos. El avatar de usuario
        queda fuera a propósito: es la foto que el propio usuario elige para su
        perfil, no un dato de terceros.

        El barrido incluye los serializers del **panel** (US-042, escenario 6):
        no hay forma de publicar una imagen sin difuminar por ningún camino, y
        que el panel no escriba fotos hoy no alcanza como garantía si nada lo
        verifica.
        """
        writable = []
        for module in (report_serializers, report_panel_serializers):
            for name in dir(module):
                candidate = getattr(module, name)
                if not (
                    isinstance(candidate, type)
                    and issubclass(candidate, serializers.Serializer)
                ):
                    continue
                if candidate.__module__ != module.__name__:
                    continue
                if "Create" not in name and "Update" not in name:
                    continue
                for field_name, field in candidate().fields.items():
                    writable_photo = (
                        isinstance(field, serializers.ImageField)
                        and not field.read_only
                    )
                    if writable_photo:
                        writable.append((name, field_name, type(field)))

        assert len(writable) == WRITABLE_PHOTOS
        assert all(field is PendingPhotoField for *_, field in writable), writable

    def test_the_admin_cannot_upload_a_photo_or_force_its_state(self):
        """Ni la foto ni el estado del procesamiento se editan desde el admin.

        Poder escribir `photo_status` a mano sería la vía degradada que la
        historia descarta: marcar «procesada» una imagen que nunca pasó por el
        servicio la publicaría igual.
        """
        for field in ("photo", "photo_pending", "photo_status", "photo_failed_at"):
            assert field in ReportAdmin.readonly_fields
