from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from urbancheck.notifications.models import Notification
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


class NotificationFactory(DjangoModelFactory[Notification]):
    recipient = factory.SubFactory(UserFactory)
    actor = factory.SubFactory(UserFactory)
    kind = Notification.Kind.NUEVO_COMENTARIO
    report = factory.SubFactory(ReportFactory)
    message = factory.Faker("sentence")

    class Meta:
        model = Notification
