"""US-009: borrado de comentarios y aviso al autor del reporte."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.reports.models import Comment
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestCommentDelete:
    def test_author_can_delete_own_comment(self, auth_client):
        client, user = auth_client
        comment = CommentFactory.create(author=user)
        res = client.delete(f"/api/comments/{comment.id}/")
        assert res.status_code == 204
        assert not Comment.objects.filter(id=comment.id).exists()

    def test_cannot_delete_someone_elses_comment(self, auth_client):
        client, _ = auth_client
        comment = CommentFactory.create()
        res = client.delete(f"/api/comments/{comment.id}/")
        assert res.status_code == 403
        assert Comment.objects.filter(id=comment.id).exists()

    def test_deleted_comment_disappears_from_list(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report, author=user)
        client.delete(f"/api/comments/{comment.id}/")
        res = client.get(f"/api/reports/{report.id}/comments/")
        assert comment.id not in {c["id"] for c in res.data}

    def test_is_mine_flag(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create()
        mine = CommentFactory.create(report=report, author=user)
        theirs = CommentFactory.create(report=report)
        res = client.get(f"/api/reports/{report.id}/comments/")
        by_id = {c["id"]: c for c in res.data}
        assert by_id[mine.id]["is_mine"] is True
        assert by_id[theirs.id]["is_mine"] is False


@pytest.mark.django_db
class TestReportAuthorModeratesItsComments:
    """El dueño de la publicación borra lo que le cuelgan.

    Es un derecho distinto del de borrar lo propio, y los dos son razonables:
    uno se arrepiente de lo que escribió, y el otro modera su publicación.
    """

    def test_the_report_author_can_delete_a_comment_of_someone_else(self, auth_client):
        client, user = auth_client
        report = ReportFactory.create(author=user)
        comment = CommentFactory.create(report=report)

        res = client.delete(f"/api/comments/{comment.id}/")

        assert res.status_code == 204
        assert not Comment.objects.filter(id=comment.id).exists()

    def test_a_stranger_still_cannot(self, auth_client):
        """No es una puerta abierta: sigue haciendo falta ser uno de los dos."""
        client, _ = auth_client
        comment = CommentFactory.create(report=ReportFactory.create())

        res = client.delete(f"/api/comments/{comment.id}/")

        assert res.status_code == 403
        assert Comment.objects.filter(id=comment.id).exists()

    def test_can_delete_tells_the_client_which_ones(self, auth_client):
        """El cliente muestra el botón por esto, no replicando la regla."""
        client, user = auth_client
        own_report = ReportFactory.create(author=user)
        mine = CommentFactory.create(report=own_report, author=user)
        on_my_report = CommentFactory.create(report=own_report)
        elsewhere = CommentFactory.create(report=ReportFactory.create())

        res = client.get(f"/api/reports/{own_report.id}/comments/")
        rows = {c["id"]: c for c in res.data}
        assert rows[mine.id]["can_delete"] is True
        assert rows[on_my_report.id]["can_delete"] is True

        foreign = client.get(f"/api/reports/{elsewhere.report_id}/comments/")
        assert {c["id"]: c for c in foreign.data}[elsewhere.id]["can_delete"] is False

    def test_my_comment_on_someone_elses_report_is_still_mine_to_delete(
        self,
        auth_client,
    ):
        client, user = auth_client
        comment = CommentFactory.create(author=user, report=ReportFactory.create())

        res = client.delete(f"/api/comments/{comment.id}/")

        assert res.status_code == 204


@pytest.mark.django_db
class TestCommentNotification:
    def test_report_author_is_notified(self, auth_client):
        client, commenter = auth_client
        owner = UserFactory.create()
        report = ReportFactory.create(author=owner)

        res = client.post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Yo también lo vi"},
            format="json",
        )
        assert res.status_code == 201

        notification = Notification.objects.get(recipient=owner)
        assert notification.kind == Notification.Kind.NUEVO_COMENTARIO
        assert notification.actor == commenter
        assert notification.report == report
        assert notification.is_read is False

    def test_no_self_notification(self, auth_client):
        """Comentar el propio reporte no genera un aviso para uno mismo."""
        client, user = auth_client
        report = ReportFactory.create(author=user)
        client.post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Agrego un dato"},
            format="json",
        )
        assert not Notification.objects.filter(recipient=user).exists()

    def test_notification_message_includes_preview(self, auth_client):
        client, commenter = auth_client
        owner = UserFactory.create(name="Ana")
        report = ReportFactory.create(author=owner)
        client.post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Está peor que ayer"},
            format="json",
        )
        notification = Notification.objects.get(recipient=owner)
        assert "Está peor que ayer" in notification.message
        assert (commenter.name or commenter.email) in notification.message
