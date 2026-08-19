"""US-009: bandeja de notificaciones del usuario."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.notifications.tests.factories import NotificationFactory
from urbancheck.users.tests.factories import UserFactory


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestNotificationList:
    def test_only_own_notifications(self, auth_client):
        client, user = auth_client
        mine = NotificationFactory.create(recipient=user)
        NotificationFactory.create()  # de otro usuario
        res = client.get("/api/notifications/")
        assert res.status_code == 200
        assert {n["id"] for n in res.data["results"]} == {mine.id}

    def test_newest_first(self, auth_client):
        client, user = auth_client
        older = NotificationFactory.create(recipient=user)
        newer = NotificationFactory.create(recipient=user)
        res = client.get("/api/notifications/")
        assert [n["id"] for n in res.data["results"]] == [newer.id, older.id]

    def test_unread_filter(self, auth_client):
        client, user = auth_client
        unread = NotificationFactory.create(recipient=user, is_read=False)
        NotificationFactory.create(recipient=user, is_read=True)
        res = client.get("/api/notifications/?unread=true")
        assert {n["id"] for n in res.data["results"]} == {unread.id}

    def test_payload_includes_report_id_for_navigation(self, auth_client):
        client, user = auth_client
        notification = NotificationFactory.create(recipient=user)
        res = client.get("/api/notifications/")
        assert res.data["results"][0]["report_id"] == notification.report_id

    def test_anonymous_denied(self, db):
        res = APIClient().get("/api/notifications/")
        assert res.status_code in (401, 403)


@pytest.mark.django_db
class TestNotificationRead:
    def test_unread_count(self, auth_client):
        client, user = auth_client
        NotificationFactory.create_batch(3, recipient=user, is_read=False)
        NotificationFactory.create(recipient=user, is_read=True)
        NotificationFactory.create()  # de otro usuario
        res = client.get("/api/notifications/unread_count/")
        assert res.data == {"unread": 3}

    def test_mark_single_as_read(self, auth_client):
        client, user = auth_client
        notification = NotificationFactory.create(recipient=user, is_read=False)
        res = client.post(f"/api/notifications/{notification.id}/read/")
        assert res.status_code == 200
        assert res.data["is_read"] is True
        notification.refresh_from_db()
        assert notification.is_read is True

    def test_mark_all_as_read(self, auth_client):
        client, user = auth_client
        NotificationFactory.create_batch(2, recipient=user, is_read=False)
        other = NotificationFactory.create(is_read=False)
        res = client.post("/api/notifications/read_all/")
        assert res.data == {"updated": 2}
        assert not Notification.objects.filter(recipient=user, is_read=False).exists()
        other.refresh_from_db()
        assert other.is_read is False

    def test_cannot_read_someone_elses_notification(self, auth_client):
        client, _ = auth_client
        other = NotificationFactory.create()
        res = client.post(f"/api/notifications/{other.id}/read/")
        assert res.status_code == 404

    def test_delete_own_notification(self, auth_client):
        client, user = auth_client
        notification = NotificationFactory.create(recipient=user)
        res = client.delete(f"/api/notifications/{notification.id}/")
        assert res.status_code == 204
        assert not Notification.objects.filter(id=notification.id).exists()
