from __future__ import annotations

import pytest
from django.db.models import Count
from rest_framework.test import APIRequestFactory

from urbancheck.reports.api.serializers import ReportCreateSerializer
from urbancheck.reports.api.serializers import ReportDetailSerializer
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


def make_photo():
    from urbancheck.reports.tests.test_views import make_image_file

    return make_image_file()


class TestReportCreateSerializer:
    def _data(self, **overrides):
        data = {
            "photo": make_photo(),
            "description": "Bache profundo",
            "category": "bache",
            "latitude": "-34.6",
            "longitude": "-58.4",
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not None}

    @pytest.mark.django_db
    def test_valid_with_coords(self):
        serializer = ReportCreateSerializer(data=self._data())
        assert serializer.is_valid(), serializer.errors

    @pytest.mark.django_db
    def test_valid_with_address_only(self):
        serializer = ReportCreateSerializer(
            data=self._data(latitude=None, longitude=None, address="Av. Corrientes 1234"),
        )
        assert serializer.is_valid(), serializer.errors

    @pytest.mark.django_db
    def test_missing_photo_is_invalid(self):
        serializer = ReportCreateSerializer(data=self._data(photo=None))
        assert not serializer.is_valid()
        assert "photo" in serializer.errors

    @pytest.mark.django_db
    def test_missing_location_is_invalid(self):
        serializer = ReportCreateSerializer(data=self._data(latitude=None, longitude=None))
        assert not serializer.is_valid()
        assert "location" in serializer.errors

    @pytest.mark.django_db
    def test_whitespace_address_does_not_count_as_location(self):
        serializer = ReportCreateSerializer(
            data=self._data(latitude=None, longitude=None, address="   "),
        )
        assert not serializer.is_valid()
        assert "location" in serializer.errors

    @pytest.mark.django_db
    def test_only_latitude_is_invalid(self):
        serializer = ReportCreateSerializer(data=self._data(longitude=None))
        assert not serializer.is_valid()
        assert "location" in serializer.errors

    @pytest.mark.django_db
    def test_invalid_category_rejected(self):
        serializer = ReportCreateSerializer(data=self._data(category="inexistente"))
        assert not serializer.is_valid()
        assert "category" in serializer.errors


@pytest.mark.django_db
class TestReportDetailSerializer:
    def _serialize(self, report, user=None):
        factory = APIRequestFactory()
        request = factory.get(f"/api/reports/{report.id}/")
        request.user = user or UserFactory.create()
        annotated = Report.objects.annotate(
            like_count=Count("likes", distinct=True),
            comment_count=Count("comments", distinct=True),
        ).get(id=report.id)
        return ReportDetailSerializer(annotated, context={"request": request}).data

    def test_is_liked_true_when_user_liked(self):
        report = ReportFactory.create()
        user = UserFactory.create()
        LikeFactory.create(report=report, user=user)
        data = self._serialize(report, user=user)
        assert data["is_liked"] is True

    def test_is_liked_false_for_other_user(self):
        report = ReportFactory.create()
        LikeFactory.create(report=report)
        data = self._serialize(report)
        assert data["is_liked"] is False

    def test_includes_comments_and_history(self):
        report = ReportFactory.create()
        CommentFactory.create_batch(2, report=report)
        data = self._serialize(report)
        assert len(data["comments"]) == 2
        assert len(data["status_history"]) == 1
        assert data["status_history"][0]["status"] == report.status

    def test_comments_include_author(self):
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report)
        data = self._serialize(report)
        assert data["comments"][0]["author"]["id"] == comment.author.id
        assert data["comments"][0]["text"] == comment.text
