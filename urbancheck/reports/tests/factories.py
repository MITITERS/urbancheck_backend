from __future__ import annotations

import factory
from factory.django import DjangoModelFactory
from factory.django import ImageField

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.users.tests.factories import UserFactory


class ReportFactory(DjangoModelFactory[Report]):
    author = factory.SubFactory(UserFactory)
    municipality = factory.SubFactory(MunicipalityFactory)
    photo = ImageField(filename="report.jpg")
    description = factory.Faker("sentence", nb_words=10)
    category = Report.Category.BACHE
    latitude = factory.Faker("latitude")
    longitude = factory.Faker("longitude")
    status = Report.Status.REPORTADO

    class Meta:
        model = Report

    @factory.post_generation
    def with_history(self, create, extracted, **kwargs):
        if create and extracted is not False:
            ReportStatusHistory.objects.create(
                report=self,
                status=self.status,
                changed_by=self.author,
            )


class CommentFactory(DjangoModelFactory[Comment]):
    report = factory.SubFactory(ReportFactory)
    author = factory.SubFactory(UserFactory)
    text = factory.Faker("sentence")

    class Meta:
        model = Comment


class LikeFactory(DjangoModelFactory[Like]):
    report = factory.SubFactory(ReportFactory)
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = Like
