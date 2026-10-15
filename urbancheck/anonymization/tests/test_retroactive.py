"""Fotos que no pasan por el circuito, y las que llegaron antes de él.

- La foto de perfil se guarda sin metadatos, venga por donde venga (SEC-09).
- ``strip_image_metadata`` sanea las de perfil ya guardadas (SEC-10).
- ``anonymize_existing_photos`` difumina las fotos publicadas antes de US-041
  (US-042, escenario 9).

Los dos comandos son simulacros sin ``--apply``: eso también se prueba, porque
tocan archivos publicados y el equipo tiene que poder ver qué harían antes.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.anonymization.tests.images import assert_no_metadata
from urbancheck.anonymization.tests.images import synthetic_photo
from urbancheck.notifications.models import Notification
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def run(command: str, *args) -> str:
    out = io.StringIO()
    call_command(command, *args, stdout=out, stderr=io.StringIO())
    return out.getvalue()


def with_raw_avatar(user, data: bytes, name: str = "perfil.jpg") -> Path:
    """Escribe el avatar tal cual, como quedó guardado antes del Sprint 5."""
    path = Path(user.avatar.storage.save(f"avatars/{name}", ContentFile(data)))
    type(user).objects.filter(pk=user.pk).update(avatar=str(path))
    user.refresh_from_db()
    return Path(user.avatar.path)


class TestProfilePhoto:
    def test_the_api_stores_it_without_metadata(self):
        """CP-SEC09-01: la foto de perfil subida por la API, sin GPS ni EXIF."""
        user = UserFactory.create()
        client = APIClient()
        client.force_authenticate(user)

        response = client.patch(
            "/api/users/me/",
            {
                "avatar": SimpleUploadedFile(
                    "perfil.jpg",
                    synthetic_photo(),
                    content_type="image/jpeg",
                ),
            },
            format="multipart",
        )

        assert response.status_code == 200  # noqa: PLR2004
        user.refresh_from_db()
        assert_no_metadata(Path(user.avatar.path).read_bytes())

    def test_any_other_path_stores_it_without_metadata_too(self):
        """CP-SEC09-02: el admin y el shell pasan por el mismo campo."""
        user = UserFactory.create()

        user.avatar = ContentFile(synthetic_photo(), name="perfil.jpg")
        user.save()

        assert_no_metadata(Path(user.avatar.path).read_bytes())

    def test_the_orientation_is_applied_before_dropping_it(self):
        """CP-SEC09-03: la rotación del EXIF queda en los píxeles."""
        user = UserFactory.create()
        user.avatar = ContentFile(
            synthetic_photo((60, 20), orientation=6),
            name="perfil.jpg",
        )
        user.save()

        assert Image.open(user.avatar.path).size == (20, 60)

    def test_it_is_not_blurred(self):
        """CP-SEC09-04: el perfil no se difumina: es la foto que eligió mostrar."""
        user = UserFactory.create()
        data = synthetic_photo()
        user.avatar = ContentFile(data, name="perfil.jpg")
        user.save()

        before = Image.open(io.BytesIO(data)).convert("RGB")
        after = Image.open(user.avatar.path).convert("RGB")
        assert before.size == after.size


class TestStripImageMetadata:
    def test_without_apply_it_only_counts(self):
        """CP-SEC10-01: el simulacro no toca nada."""
        user = UserFactory.create()
        path = with_raw_avatar(user, synthetic_photo())
        original = path.read_bytes()

        output = run("strip_image_metadata")

        assert "1 fotos de perfil por sanear" in output
        assert path.read_bytes() == original

    def test_it_rewrites_stored_avatars_without_metadata(
        self,
        django_capture_on_commit_callbacks,
    ):
        """CP-SEC10-02: el avatar viejo queda sin GPS y el archivo viejo se borra."""
        user = UserFactory.create()
        old = with_raw_avatar(user, synthetic_photo())

        with django_capture_on_commit_callbacks(execute=True):
            output = run("strip_image_metadata", "--apply")

        user.refresh_from_db()
        assert "1 saneadas" in output
        assert_no_metadata(Path(user.avatar.path).read_bytes())
        assert not old.exists()

    def test_an_unreadable_file_is_left_alone(self):
        """CP-SEC10-03: un archivo roto se informa y no se pierde."""
        user = UserFactory.create()
        old = with_raw_avatar(user, b"no es una imagen", "roto.jpg")

        output = run("strip_image_metadata", "--apply")

        user.refresh_from_db()
        assert "1 ilegibles" in output
        assert Path(user.avatar.path) == old
        assert old.exists()


@pytest.fixture
def legacy_report():
    """Un reporte de antes de US-041: publicado, con cero intentos y con GPS."""
    report = ReportFactory.create(photo_attempts=0)
    report.photo.storage.delete(report.photo.name)
    name = report.photo.storage.save(report.photo.name, ContentFile(synthetic_photo()))
    Report.objects.filter(pk=report.pk).update(photo=name)
    report.refresh_from_db()
    return report


class TestAnonymizeExistingPhotos:
    def test_without_apply_it_only_counts(self, legacy_report):
        """CP-042-09: el simulacro cuenta y no toca nada."""
        original = Path(legacy_report.photo.path).read_bytes()

        output = run("anonymize_existing_photos")

        assert "Simulacro: 1 fotos por procesar" in output
        legacy_report.refresh_from_db()
        assert Path(legacy_report.photo.path).read_bytes() == original
        assert legacy_report.photo_attempts == 0

    def test_it_replaces_the_published_photo_with_the_anonymized_one(
        self,
        legacy_report,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-10: queda solo la versión procesada; la vieja se borra."""
        old = Path(legacy_report.photo.path)

        with django_capture_on_commit_callbacks(execute=True):
            run("anonymize_existing_photos", "--apply")

        legacy_report.refresh_from_db()
        assert legacy_report.photo_attempts == 1
        assert legacy_report.photo_status == PhotoStatus.PROCESADA
        assert Path(legacy_report.photo.path) != old
        assert not old.exists()
        assert_no_metadata(Path(legacy_report.photo.path).read_bytes())

    def test_running_it_twice_changes_nothing(
        self,
        legacy_report,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-11: idempotente."""
        with django_capture_on_commit_callbacks(execute=True):
            run("anonymize_existing_photos", "--apply")
        legacy_report.refresh_from_db()
        first = legacy_report.photo.name

        with django_capture_on_commit_callbacks(execute=True):
            output = run("anonymize_existing_photos", "--apply")

        legacy_report.refresh_from_db()
        assert legacy_report.photo.name == first
        assert "0 difuminadas" in output

    def test_photos_that_already_went_through_the_service_are_left_alone(self):
        """CP-042-12: lo que procesó el circuito de US-042 no se reprocesa."""
        report = ReportFactory.create(photo_attempts=1)
        name = report.photo.name

        run("anonymize_existing_photos", "--apply")

        report.refresh_from_db()
        assert report.photo.name == name

    def test_a_photo_that_cannot_be_processed_is_withdrawn(
        self,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-13: no queda publicada sin difuminar; el autor se entera."""
        report = ReportFactory.create(photo_attempts=0)
        path = Path(report.photo.path)
        path.write_bytes(b"no es una imagen")

        with django_capture_on_commit_callbacks(execute=True):
            output = run("anonymize_existing_photos", "--apply")

        report.refresh_from_db()
        assert "1 retiradas" in output
        assert not report.photo
        assert report.photo_status == PhotoStatus.FALLIDA
        assert not Report.objects.publicly_visible().filter(pk=report.pk).exists()
        assert not path.exists()
        assert Notification.objects.filter(recipient=report.author).exists()
