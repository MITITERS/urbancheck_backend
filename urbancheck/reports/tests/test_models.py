from __future__ import annotations

import pytest
from django.db import IntegrityError

from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestReport:
    def test_str(self):
        report = ReportFactory.create(category=Report.Category.BACHE)
        assert str(report) == f"bache — {report.author} ({report.status})"

    def test_default_status_is_pendiente_validacion(self, active_municipality):
        report = Report.objects.create(
            author=UserFactory.create(),
            municipality=active_municipality,
            photo="reports/2026/07/test.jpg",
            description="Bache en la esquina",
            category=Report.Category.BACHE,
            latitude="-34.6",
            longitude="-58.4",
        )
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    def test_ordering_newest_first(self):
        older = ReportFactory.create()
        newer = ReportFactory.create()
        assert list(Report.objects.all()) == [newer, older]

    def test_deleting_author_deletes_reports(self):
        report = ReportFactory.create()
        report.author.delete()
        assert not Report.objects.filter(id=report.id).exists()


@pytest.mark.django_db
class TestReportStatusHistory:
    def test_deleting_report_deletes_history(self):
        report = ReportFactory.create()
        assert report.status_history.exists()
        report.delete()
        assert not ReportStatusHistory.objects.filter(report_id=report.id).exists()

    def test_deleting_changed_by_keeps_history(self):
        user = UserFactory.create()
        report = ReportFactory.create(with_history=False)
        entry = ReportStatusHistory.objects.create(
            report=report,
            status=Report.Status.REPORTADO,
            changed_by=user,
        )
        user.delete()
        entry.refresh_from_db()
        assert entry.changed_by is None

    def test_ordering_newest_first(self):
        report = ReportFactory.create(with_history=False)
        first = ReportStatusHistory.objects.create(
            report=report, status=Report.Status.PENDIENTE_VALIDACION
        )
        second = ReportStatusHistory.objects.create(
            report=report, status=Report.Status.REPORTADO
        )
        assert list(report.status_history.all()) == [second, first]


@pytest.mark.django_db
class TestComment:
    def test_deleting_report_deletes_comments(self):
        comment = CommentFactory.create()
        comment.report.delete()
        assert not Comment.objects.filter(id=comment.id).exists()

    def test_ordering_newest_first(self):
        report = ReportFactory.create()
        first = CommentFactory.create(report=report)
        second = CommentFactory.create(report=report)
        assert list(report.comments.all()) == [second, first]


@pytest.mark.django_db
class TestLike:
    def test_unique_per_report_and_user(self):
        like = LikeFactory.create()
        with pytest.raises(IntegrityError):
            Like.objects.create(report=like.report, user=like.user)

    def test_same_user_can_like_different_reports(self):
        user = UserFactory.create()
        LikeFactory.create(user=user)
        LikeFactory.create(user=user)
        assert user.likes.count() == 2

    def test_deleting_report_deletes_likes(self):
        like = LikeFactory.create()
        like.report.delete()
        assert not Like.objects.filter(id=like.id).exists()
