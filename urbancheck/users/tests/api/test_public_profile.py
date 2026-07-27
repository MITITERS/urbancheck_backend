"""US-027: perfil público de otro usuario."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestPublicProfile:
    def test_shows_name_join_date_and_report_count(self, auth_client):
        client, _ = auth_client
        other = UserFactory.create(name="Carla")
        ReportFactory.create_batch(2, author=other)

        res = client.get(f"/api/users/{other.id}/")
        assert res.status_code == 200
        assert res.data["name"] == "Carla"
        assert res.data["date_joined"] is not None
        assert res.data["report_count"] == 2
        assert "avatar" in res.data

    def test_does_not_leak_email(self, auth_client):
        client, _ = auth_client
        other = UserFactory.create()
        res = client.get(f"/api/users/{other.id}/")
        assert "email" not in res.data

    def test_private_profile_hides_details(self, auth_client):
        client, _ = auth_client
        other = UserFactory.create(name="Reservado", is_public=False)
        ReportFactory.create_batch(3, author=other)

        res = client.get(f"/api/users/{other.id}/")
        assert res.status_code == 200
        assert res.data["name"] == "Reservado"
        assert res.data["is_public"] is False
        assert res.data["date_joined"] is None
        assert res.data["report_count"] is None

    def test_own_profile_still_returns_full_data(self, auth_client):
        client, user = auth_client
        res = client.get(f"/api/users/{user.id}/")
        assert res.status_code == 200
        assert res.data["email"] == user.email

    def test_anonymous_denied(self, db):
        other = UserFactory.create()
        res = APIClient().get(f"/api/users/{other.id}/")
        assert res.status_code in (401, 403)


@pytest.mark.django_db
class TestPublicProfileReports:
    def test_lists_reports_newest_first(self, auth_client):
        client, _ = auth_client
        other = UserFactory.create()
        older = ReportFactory.create(author=other)
        newer = ReportFactory.create(author=other)
        ReportFactory.create()  # de un tercero

        res = client.get(f"/api/reports/?author={other.id}")
        assert res.status_code == 200
        assert [r["id"] for r in res.data["results"]] == [newer.id, older.id]

    def test_private_profile_reports_are_hidden(self, auth_client):
        client, _ = auth_client
        other = UserFactory.create(is_public=False)
        ReportFactory.create_batch(2, author=other)

        res = client.get(f"/api/reports/?author={other.id}")
        assert res.data["count"] == 0

    def test_own_reports_visible_even_if_private(self, auth_client):
        client, user = auth_client
        user.is_public = False
        user.save(update_fields=["is_public"])
        ReportFactory.create_batch(2, author=user)

        res = client.get(f"/api/reports/?author={user.id}")
        assert res.data["count"] == 2


@pytest.mark.django_db
class TestPrivacyToggle:
    def test_user_can_make_profile_private(self, auth_client):
        client, user = auth_client
        assert user.is_public is True
        res = client.patch("/api/users/me/", data={"is_public": False}, format="json")
        assert res.status_code == 200
        user.refresh_from_db()
        assert user.is_public is False

    def test_cannot_edit_another_user(self, auth_client):
        client, _ = auth_client
        other = UserFactory.create(name="Intacto")
        res = client.patch(
            f"/api/users/{other.id}/", data={"name": "Hackeado"}, format="json"
        )
        assert res.status_code == 404
        other.refresh_from_db()
        assert other.name == "Intacto"
