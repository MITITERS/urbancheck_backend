"""Disparadores de avisos (US-009).

Son funciones explícitas y no señales de Django, justamente para poder probarlas
sin montar la vista que las provoca.
"""

from __future__ import annotations

import pytest

from urbancheck.notifications.models import Notification
from urbancheck.notifications.services import notify_new_comment
from urbancheck.notifications.services import notify_status_change
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

PREVIEW_LENGTH = 60


@pytest.mark.django_db
class TestNotifyNewComment:
    def test_creates_notification_for_the_report_author(self):
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report)

        notification = notify_new_comment(comment)

        assert notification is not None
        assert notification.recipient == report.author
        assert notification.actor == comment.author
        assert notification.kind == Notification.Kind.NUEVO_COMENTARIO
        assert notification.report == report

    def test_returns_none_when_the_author_comments_their_own_report(self):
        author = UserFactory.create()
        report = ReportFactory.create(author=author)
        comment = CommentFactory.create(report=report, author=author)

        assert notify_new_comment(comment) is None
        assert Notification.objects.count() == 0

    def test_message_includes_the_author_name_and_the_text(self):
        report = ReportFactory.create()
        comment = CommentFactory.create(
            report=report,
            author=UserFactory.create(name="Ana Pérez"),
            text="El bache creció",
        )

        notification = notify_new_comment(comment)

        assert "Ana Pérez" in notification.message
        assert "El bache creció" in notification.message

    def test_long_comment_is_truncated_with_ellipsis(self):
        """Entra en una línea de la bandeja; el texto completo está en el detalle."""
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report, text="x" * 200)

        notification = notify_new_comment(comment)

        assert "…" in notification.message
        assert "x" * (PREVIEW_LENGTH + 1) not in notification.message

    def test_short_comment_is_not_truncated(self):
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report, text="Sigue igual")

        assert "…" not in notify_new_comment(comment).message

    def test_falls_back_to_the_email_when_there_is_no_name(self):
        report = ReportFactory.create()
        commenter = UserFactory.create(name="", email="vecino@example.com")
        comment = CommentFactory.create(report=report, author=commenter)

        assert "vecino@example.com" in notify_new_comment(comment).message

    def test_message_fits_the_column(self):
        """``message`` es un CharField(255): un comentario largo no debe desbordarlo."""
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report, text="y" * 5000)

        notification = notify_new_comment(comment)

        max_length = Notification._meta.get_field("message").max_length  # noqa: SLF001
        assert len(notification.message) <= max_length


@pytest.mark.django_db
class TestNotifyStatusChange:
    def test_notifies_the_author_with_the_readable_label(self):
        report = ReportFactory.create(status=Report.Status.EN_PROCESO)
        municipal = UserFactory.create()

        notification = notify_status_change(report, changed_by=municipal)

        assert notification.recipient == report.author
        assert notification.kind == Notification.Kind.CAMBIO_ESTADO
        assert notification.actor == municipal
        assert "En proceso" in notification.message

    def test_system_change_leaves_the_actor_empty(self):
        report = ReportFactory.create(status=Report.Status.RESUELTO)

        notification = notify_status_change(report)

        assert notification.actor is None
        assert "Resuelto" in notification.message

    def test_returns_none_when_the_author_changed_it_themselves(self):
        author = UserFactory.create()
        report = ReportFactory.create(author=author, status=Report.Status.RESUELTO)

        assert notify_status_change(report, changed_by=author) is None
        assert Notification.objects.count() == 0
