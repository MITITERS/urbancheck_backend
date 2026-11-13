"""N-09 y N-17: el vecino borra su cuenta (derecho de supresión, Ley 25.326).

Decisión del equipo:
- confirma con su contraseña;
- se borran los reportes que el municipio nunca gestionó (pendientes de
  validación, o cancelados o archivados sin haber salido de ahí);
- los que tuvieron gestión municipal se conservan sin autor, con sus
  apelaciones también sin autor;
- se borran sus comentarios y sus me gusta;
- los avisos de otros vecinos que lo nombraban pasan a decir "Usuario eliminado";
- las cuentas de trabajo no se borran a sí mismas: siguen con la baja lógica.
"""

from __future__ import annotations

import io
import logging

import pytest
from django.contrib.sessions.models import Session
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.notifications.services import notify_new_comment
from urbancheck.notifications.services import notify_new_like
from urbancheck.notifications.services import notify_status_change
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionAppealFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

URL = "/api/users/me/"
PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105
DELETED = "Usuario eliminado"
Status = Report.Status


def with_password(user: User) -> User:
    user.set_password(PASSWORD)
    user.save()
    return user


def delete_account(user: User, password: str | None = PASSWORD):
    client = APIClient()
    client.force_authenticate(user)
    data = {} if password is None else {"password": password}
    return client.delete(URL, data, format="json")


def jpeg(name: str) -> ContentFile:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "JPEG")
    return ContentFile(buffer.getvalue(), name=name)


@pytest.fixture
def citizen() -> User:
    return with_password(UserFactory.create(name="Vecina Borrada"))


class TestConfirmation:
    def test_with_the_password_the_account_is_deleted(
        self,
        citizen,
        caplog,
        django_capture_on_commit_callbacks,
    ):
        caplog.set_level(logging.INFO, logger="security")
        pk = citizen.pk

        with django_capture_on_commit_callbacks(execute=True):
            response = delete_account(citizen)

        assert response.status_code == 204  # noqa: PLR2004
        assert not User.objects.filter(pk=pk).exists()
        events = [
            record.security
            for record in caplog.records
            if record.name == "security" and hasattr(record, "security")
        ]
        [event] = [e for e in events if e["event"] == "account_deleted"]
        assert event["user_id"] == pk
        assert PASSWORD not in caplog.text

    @pytest.mark.parametrize("password", [None, "", "incorrecta"])
    def test_without_the_right_password_nothing_happens(self, citizen, password):
        response = delete_account(citizen, password)

        assert response.status_code == 400  # noqa: PLR2004
        assert User.objects.filter(pk=citizen.pk).exists()

    def test_it_needs_a_session(self):
        response = APIClient().delete(URL, {"password": PASSWORD}, format="json")

        assert response.status_code == 403  # noqa: PLR2004

    def test_it_is_rate_limited(self, citizen):
        for _ in range(5):
            delete_account(citizen, "incorrecta")

        response = delete_account(citizen, PASSWORD)

        assert response.status_code == 429  # noqa: PLR2004
        assert User.objects.filter(pk=citizen.pk).exists()

    def test_the_other_sessions_are_closed(self, citizen, client):
        client.force_login(citizen)
        assert Session.objects.count() == 1

        delete_account(citizen)

        assert Session.objects.count() == 0


@pytest.mark.parametrize(
    "factory",
    [PlatformAdminFactory, MunicipalAgentFactory, ValidatorFactory, OperatorFactory],
)
def test_a_work_account_cannot_delete_itself(factory):
    worker = with_password(factory.create())

    response = delete_account(worker)

    assert response.status_code == 403  # noqa: PLR2004
    assert User.objects.filter(pk=worker.pk).exists()


class TestReports:
    def test_reports_the_municipality_never_handled_are_deleted(
        self,
        citizen,
        django_capture_on_commit_callbacks,
    ):
        pending = ReportFactory.create(
            author=citizen,
            status=Status.PENDIENTE_VALIDACION,
        )
        cancelled = ReportFactory.create(
            author=citizen,
            status=Status.PENDIENTE_VALIDACION,
        )
        cancelled.status = Status.CANCELADO
        cancelled.save()
        ReportStatusHistory.objects.create(
            report=cancelled,
            status=Status.CANCELADO,
            previous_status=Status.PENDIENTE_VALIDACION,
            changed_by=citizen,
        )
        archived = ReportFactory.create(
            author=citizen,
            status=Status.PENDIENTE_VALIDACION,
        )
        archived.status = Status.ARCHIVADO
        archived.save()
        ReportStatusHistory.objects.create(
            report=archived,
            status=Status.ARCHIVADO,
            previous_status=Status.PENDIENTE_VALIDACION,
        )
        photos = [r.photo.name for r in (pending, cancelled, archived)]

        with django_capture_on_commit_callbacks(execute=True):
            delete_account(citizen)

        assert not Report.objects.filter(
            pk__in=[pending.pk, cancelled.pk, archived.pk],
        ).exists()
        # N-08: sus fotos se van con ellos.
        assert not any(default_storage.exists(name) for name in photos)

    def test_handled_reports_stay_without_author(
        self,
        citizen,
        django_capture_on_commit_callbacks,
    ):
        validated = ReportFactory.create(author=citizen, status=Status.REPORTADO)
        rejected = ReportFactory.create(
            author=citizen,
            status=Status.PENDIENTE_VALIDACION,
        )
        rejected.status = Status.CANCELADO
        rejected.save()
        ReportStatusHistory.objects.create(
            report=rejected,
            status=Status.CANCELADO,
            previous_status=Status.PENDIENTE_VALIDACION,
            changed_by=ValidatorFactory.create(),
        )
        appeal = ResolutionAppealFactory.create(report=validated, author=citizen)

        with django_capture_on_commit_callbacks(execute=True):
            delete_account(citizen)

        for report in (validated, rejected):
            report.refresh_from_db()
            assert report.author_id is None
            assert default_storage.exists(report.photo.name)
        appeal.refresh_from_db()
        assert appeal.author_id is None
        assert ResolutionAppeal.objects.filter(pk=appeal.pk).exists()

    def test_a_kept_report_shows_no_author_to_others(self, citizen):
        report = ReportFactory.create(author=citizen, status=Status.REPORTADO)
        delete_account(citizen)

        client = APIClient()
        client.force_authenticate(UserFactory.create())
        response = client.get(f"/api/reports/{report.pk}/")

        assert response.status_code == 200  # noqa: PLR2004
        assert response.json()["author"] is None

    def test_a_kept_report_keeps_working_without_author(self, citizen):
        """Los avisos al autor se saltean: no hay a quién avisarle."""
        report = ReportFactory.create(author=citizen, status=Status.REPORTADO)
        delete_account(citizen)
        report.refresh_from_db()

        assert (
            notify_status_change(
                report,
                previous_status=Status.REPORTADO,
                new_status=Status.EN_PROCESO,
            )
            is None
        )
        assert notify_new_comment(CommentFactory.create(report=report)) is None
        assert notify_new_like(report, UserFactory.create()) is None


class TestActivity:
    def test_comments_and_likes_are_deleted(self, citizen):
        other = ReportFactory.create()
        CommentFactory.create(report=other, author=citizen)
        LikeFactory.create(report=other, user=citizen)

        delete_account(citizen)

        assert not Comment.objects.filter(report=other).exists()
        assert not Like.objects.filter(report=other).exists()

    def test_the_notices_of_others_say_deleted_user(self, citizen):
        other = ReportFactory.create()
        comment = CommentFactory.create(
            report=other,
            author=citizen,
            text="Mi vecina de enfrente tiene el mismo problema",
        )
        comment_notice = notify_new_comment(comment)
        like_notice = notify_new_like(other, citizen)

        delete_account(citizen)

        comment_notice.refresh_from_db()
        like_notice.refresh_from_db()
        assert comment_notice.message == f"{DELETED} comentó tu reporte."
        assert like_notice.message == f"{DELETED} apoyó tu reporte."
        assert comment_notice.actor_id is None
        texts = Notification.objects.values_list("message", flat=True)
        assert not any("Vecina Borrada" in text for text in texts)
        assert not any("vecina de enfrente" in text for text in texts)

    def test_the_avatar_file_is_deleted(
        self,
        citizen,
        django_capture_on_commit_callbacks,
    ):
        citizen.avatar = jpeg("avatar.jpg")
        citizen.save()
        name = citizen.avatar.name

        with django_capture_on_commit_callbacks(execute=True):
            delete_account(citizen)

        assert not default_storage.exists(name)
