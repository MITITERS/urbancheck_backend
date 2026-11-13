"""El aviso ``nuevo_like`` (C-09).

Existía en el catálogo y en la pantalla de preferencias, pero nada lo creaba.
Se dispara al dar me gusta, por la API, que es el único camino que existe.
"""

from __future__ import annotations

from unittest import mock

import pytest
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.notifications.models import NotificationPreference
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def like(user, report):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(f"/api/reports/{report.pk}/like/")


def unlike(user, report):
    client = APIClient()
    client.force_authenticate(user)
    return client.delete(f"/api/reports/{report.pk}/like/")


def likes_for(report):
    return Notification.objects.filter(report=report, kind=Notification.Kind.NUEVO_LIKE)


def test_the_author_is_told_who_liked_the_report():
    report = ReportFactory.create()
    neighbour = UserFactory.create(name="Ana Pérez")

    response = like(neighbour, report)

    assert response.status_code == 201  # noqa: PLR2004
    notification = likes_for(report).get()
    assert notification.recipient == report.author
    assert notification.actor == neighbour
    assert "Ana Pérez" in notification.message


def test_liking_your_own_report_says_nothing():
    report = ReportFactory.create()

    like(report.author, report)

    assert not likes_for(report).exists()


def test_one_per_person_and_report_even_after_unliking():
    report = ReportFactory.create()
    neighbour = UserFactory.create()

    like(neighbour, report)
    unlike(neighbour, report)
    like(neighbour, report)

    assert likes_for(report).count() == 1


def test_each_person_counts_once():
    report = ReportFactory.create()

    like(UserFactory.create(), report)
    like(UserFactory.create(), report)

    assert likes_for(report).count() == 2  # noqa: PLR2004


def test_the_preference_turns_off_the_push_not_the_inbox():
    """Como todo aviso (US-025): la preferencia apaga el push y nada más."""
    report = ReportFactory.create()
    NotificationPreference.objects.create(
        user=report.author,
        kind=Notification.Kind.NUEVO_LIKE,
        enabled=False,
    )

    with mock.patch("urbancheck.notifications.push.send_push") as send_push:
        like(UserFactory.create(), report)

    assert likes_for(report).count() == 1
    send_push.assert_not_called()


def test_with_the_preference_on_the_push_goes_out():
    report = ReportFactory.create()

    with mock.patch("urbancheck.notifications.push.send_push") as send_push:
        like(UserFactory.create(), report)

    send_push.assert_called_once()
