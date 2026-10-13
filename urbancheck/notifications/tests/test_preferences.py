"""US-025 — preferencias de notificaciones."""

import pytest
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.notifications.models import NotificationPreference
from urbancheck.notifications.push import deliver_push
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

URL = "/api/notification-preferences/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return UserFactory.create()


@pytest.fixture
def client(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def notification_for(user, kind) -> Notification:
    return Notification.objects.create(
        recipient=user,
        kind=kind,
        report=ReportFactory.create(author=user),
        message="mensaje",
    )


class TestCatalog:
    def test_it_lists_every_kind_of_the_catalog(self, client):
        """La pantalla se arma sola: si aparece un tipo nuevo, aparece acá."""
        response = client.get(URL)

        assert response.status_code == 200
        assert {row["kind"] for row in response.data} == set(Notification.Kind.values)

    def test_a_user_without_preferences_has_everything_enabled(self, client):
        response = client.get(URL)

        assert all(row["enabled"] for row in response.data)

    def test_each_row_carries_a_label_and_a_group(self, client):
        response = client.get(URL)

        row = next(r for r in response.data if r["kind"] == Notification.Kind.CAMBIO_ESTADO)
        assert row["label"]
        assert row["description"]
        assert row["group"] == "estado"


class TestUpdating:
    def test_disabling_a_kind_is_persisted(self, client, user):
        response = client.patch(
            URL,
            {"kind": Notification.Kind.NUEVO_LIKE, "enabled": False},
            format="json",
        )

        assert response.status_code == 200
        assert (
            NotificationPreference.is_enabled(user, Notification.Kind.NUEVO_LIKE) is False
        )

    def test_disabling_one_kind_leaves_the_others_untouched(self, client, user):
        client.patch(
            URL,
            {"kind": Notification.Kind.NUEVO_LIKE, "enabled": False},
            format="json",
        )

        assert NotificationPreference.is_enabled(user, Notification.Kind.CAMBIO_ESTADO)
        assert NotificationPreference.is_enabled(user, Notification.Kind.NUEVO_COMENTARIO)

    def test_reenabling_restores_it(self, client, user):
        kind = Notification.Kind.CAMBIO_ESTADO
        client.patch(URL, {"kind": kind, "enabled": False}, format="json")

        client.patch(URL, {"kind": kind, "enabled": True}, format="json")

        assert NotificationPreference.is_enabled(user, kind) is True

    def test_an_unknown_kind_is_rejected(self, client):
        response = client.patch(
            URL,
            {"kind": "inventado", "enabled": False},
            format="json",
        )

        assert response.status_code == 400


class TestFiltering:
    def test_a_disabled_kind_is_not_pushed(self, user, monkeypatch):
        sent = []
        monkeypatch.setattr(
            "urbancheck.notifications.push.send_push",
            lambda notification: sent.append(notification) or True,
        )
        NotificationPreference.objects.create(
            user=user,
            kind=Notification.Kind.NUEVO_LIKE,
            enabled=False,
        )

        delivered = deliver_push(notification_for(user, Notification.Kind.NUEVO_LIKE))

        assert delivered is False
        assert sent == []

    def test_the_other_kinds_keep_being_pushed(self, user, monkeypatch):
        sent = []
        monkeypatch.setattr(
            "urbancheck.notifications.push.send_push",
            lambda notification: sent.append(notification) or True,
        )
        NotificationPreference.objects.create(
            user=user,
            kind=Notification.Kind.NUEVO_LIKE,
            enabled=False,
        )

        deliver_push(notification_for(user, Notification.Kind.CAMBIO_ESTADO))

        assert len(sent) == 1

    def test_a_user_without_preferences_gets_everything(self, user, monkeypatch):
        sent = []
        monkeypatch.setattr(
            "urbancheck.notifications.push.send_push",
            lambda notification: sent.append(notification) or True,
        )

        for kind in Notification.Kind.values:
            deliver_push(notification_for(user, kind))

        assert len(sent) == len(Notification.Kind.values)

    def test_disabling_only_stops_the_push_not_the_inbox(self, user, monkeypatch):
        """Decisión documentada: el aviso igual queda en la bandeja."""
        monkeypatch.setattr(
            "urbancheck.notifications.push.send_push",
            lambda notification: True,
        )
        NotificationPreference.objects.create(
            user=user,
            kind=Notification.Kind.CAMBIO_ESTADO,
            enabled=False,
        )

        notification = notification_for(user, Notification.Kind.CAMBIO_ESTADO)
        deliver_push(notification)

        assert Notification.objects.filter(pk=notification.pk).exists()

    def test_preferences_do_not_hide_notifications_already_received(self, client, user):
        notification_for(user, Notification.Kind.NUEVO_LIKE)

        client.patch(
            URL,
            {"kind": Notification.Kind.NUEVO_LIKE, "enabled": False},
            format="json",
        )

        assert client.get("/api/notifications/").data["count"] == 1


class TestPermissions:
    def test_anonymous_is_denied(self):
        assert APIClient().get(URL).status_code == 403

    def test_preferences_are_per_user(self, client, user):
        other = UserFactory.create()
        client.patch(
            URL,
            {"kind": Notification.Kind.NUEVO_LIKE, "enabled": False},
            format="json",
        )

        assert NotificationPreference.is_enabled(other, Notification.Kind.NUEVO_LIKE)


class TestEveryKindIsDescribed:
    """El catálogo se deriva de ``Notification.Kind``, pero los textos no.

    Un tipo nuevo aparece solo en la pantalla —eso ya funcionaba— pero sin
    descripción y agrupado entre los huérfanos, que es lo que pasó al sumar los
    avisos de US-024, US-031, US-047 y US-048. Este test hace que agregar un
    tipo obligue a decidir cómo se llama y dónde va.
    """

    def test_every_kind_has_a_description_and_a_group(self, client):
        catalogue = client.get(URL).data

        assert len(catalogue) == len(Notification.Kind.values)
        for entry in catalogue:
            assert entry["description"], f"{entry['kind']} no tiene descripción"
            assert entry["group"] != "otros", f"{entry['kind']} quedó sin agrupar"
