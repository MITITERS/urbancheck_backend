"""Modelo ``Notification`` (US-009).

La bandeja se apoya en el orden por fecha y en que borrar un reporte o un usuario
no deje avisos huérfanos apuntando a algo que ya no existe.
"""

from __future__ import annotations

import pytest

from urbancheck.notifications.models import Notification
from urbancheck.notifications.tests.factories import NotificationFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestNotificationModel:
    def test_str_identifies_kind_and_recipient(self):
        notification = NotificationFactory.create()
        assert notification.kind in str(notification)
        assert str(notification.recipient) in str(notification)

    def test_starts_unread(self):
        assert NotificationFactory.create().is_read is False

    def test_ordering_newest_first(self):
        first = NotificationFactory.create()
        second = NotificationFactory.create()
        assert list(Notification.objects.all()) == [second, first]

    def test_deleting_the_report_deletes_its_notifications(self):
        """US-019: al borrar un reporte no debe quedar un aviso que no lleva a nada."""
        report = ReportFactory.create()
        NotificationFactory.create(report=report)
        report.delete()
        assert Notification.objects.count() == 0

    def test_deleting_the_recipient_deletes_their_inbox(self):
        recipient = UserFactory.create()
        NotificationFactory.create(recipient=recipient)
        recipient.delete()
        assert Notification.objects.count() == 0

    def test_deleting_the_actor_keeps_the_notification(self):
        """Si se va quien comentó, el aviso sigue siendo válido para el destinatario."""
        actor = UserFactory.create()
        notification = NotificationFactory.create(actor=actor)
        actor.delete()
        notification.refresh_from_db()
        assert notification.actor is None

    def test_report_is_optional(self):
        """Hay avisos que no cuelgan de un reporte (los genera el sistema)."""
        notification = NotificationFactory.create(report=None, actor=None)
        assert notification.report is None
