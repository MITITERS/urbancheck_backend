"""N-08: borrar un reporte o una cuenta borra también sus archivos.

La foto de un reporte, de un cierre y de una apelación, la original pendiente
y el avatar quedaban en disco después del borrado: la supresión del art. 16 de
la Ley 25.326 no era efectiva. Se borran recién al confirmarse la transacción,
para que un rollback no deje una fila apuntando a un archivo que ya no está.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import transaction
from PIL import Image

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.anonymization.storage import pending_photo_storage
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionAppealFactory
from urbancheck.reports.tests.factories import ResolutionEvidenceFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def jpeg(name: str = "foto.jpg") -> ContentFile:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "JPEG")
    return ContentFile(buffer.getvalue(), name=name)


def exists(field_file) -> bool:
    return bool(field_file.name) and field_file.storage.exists(field_file.name)


class TestDeletingRemovesTheFiles:
    def test_a_report_takes_its_photo_and_its_pending_original(
        self,
        django_capture_on_commit_callbacks,
    ):
        report = ReportFactory.create()
        report.photo_pending.save("original.jpg", jpeg(), save=False)
        photo, pending = report.photo, report.photo_pending
        assert exists(photo)
        assert exists(pending)

        with django_capture_on_commit_callbacks(execute=True):
            report.delete()

        assert not default_storage.exists(photo.name)
        assert not pending_photo_storage().exists(pending.name)

    def test_a_report_takes_its_closure_and_appeal_photos(
        self,
        django_capture_on_commit_callbacks,
    ):
        evidence = ResolutionEvidenceFactory.create()
        appeal = ResolutionAppealFactory.create(report=evidence.report)
        names = [evidence.photo.name, appeal.photo.name]

        with django_capture_on_commit_callbacks(execute=True):
            evidence.report.delete()

        assert not any(default_storage.exists(name) for name in names)

    def test_a_closure_or_appeal_deleted_alone_takes_its_photo(
        self,
        django_capture_on_commit_callbacks,
    ):
        evidence = ResolutionEvidenceFactory.create()
        appeal = ResolutionAppealFactory.create()
        names = [evidence.photo.name, appeal.photo.name]

        with django_capture_on_commit_callbacks(execute=True):
            evidence.delete()
            appeal.delete()

        assert not any(default_storage.exists(name) for name in names)

    def test_an_account_takes_its_avatar(self, django_capture_on_commit_callbacks):
        user = UserFactory.create()
        user.avatar = jpeg("avatar.jpg")
        user.save()
        name = user.avatar.name
        assert default_storage.exists(name)

        with django_capture_on_commit_callbacks(execute=True):
            user.delete()

        assert not default_storage.exists(name)

    def test_a_rolled_back_deletion_keeps_the_file(self):
        report = ReportFactory.create()
        name = report.photo.name

        def delete_and_fail():
            with transaction.atomic():
                report.delete()
                raise RuntimeError

        with pytest.raises(RuntimeError):
            delete_and_fail()

        assert default_storage.exists(name)


class TestReplacingRemovesTheOldFile:
    def test_a_new_avatar(self, django_capture_on_commit_callbacks):
        user = UserFactory.create()
        user.avatar = jpeg("primero.jpg")
        user.save()
        old = user.avatar.name

        with django_capture_on_commit_callbacks(execute=True):
            user.avatar = jpeg("segundo.jpg")
            user.save()

        assert not default_storage.exists(old)
        assert default_storage.exists(user.avatar.name)

    def test_removing_the_avatar(self, django_capture_on_commit_callbacks):
        user = UserFactory.create()
        user.avatar = jpeg("avatar.jpg")
        user.save()
        old = user.avatar.name

        with django_capture_on_commit_callbacks(execute=True):
            user.avatar = ""
            user.save()

        assert not default_storage.exists(old)

    def test_a_new_report_photo(self, django_capture_on_commit_callbacks):
        report = ReportFactory.create()
        old = report.photo.name

        with django_capture_on_commit_callbacks(execute=True):
            report.photo = jpeg("nueva.jpg")
            report.photo_status = PhotoStatus.PROCESADA
            report.save()

        assert not default_storage.exists(old)
        assert default_storage.exists(report.photo.name)

    def test_saving_without_touching_the_photo_keeps_it(
        self,
        django_capture_on_commit_callbacks,
    ):
        report = ReportFactory.create()

        with django_capture_on_commit_callbacks(execute=True):
            report.description = "Otra descripción"
            report.save()

        assert default_storage.exists(report.photo.name)


class TestPurgeOrphanMedia:
    @pytest.fixture
    def orphan(self, settings) -> Path:
        path = Path(settings.MEDIA_ROOT) / "reports" / "2026" / "01" / "huerfana.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    def test_it_only_lists_without_apply(self, orphan, capsys):
        kept = ReportFactory.create()

        call_command("purge_orphan_media")

        out = capsys.readouterr().out
        assert "reports/2026/01/huerfana.jpg" in out
        assert kept.photo.name not in out
        assert orphan.exists()

    def test_with_apply_it_deletes_only_the_orphans(self, orphan):
        kept = ReportFactory.create()

        call_command("purge_orphan_media", "--apply")

        assert not orphan.exists()
        assert default_storage.exists(kept.photo.name)
