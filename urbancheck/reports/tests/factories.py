from __future__ import annotations

import factory
from factory.django import DjangoModelFactory
from factory.django import ImageField

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.users.tests.factories import OperatorFactory
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


def area_for(report):
    """Área operativa activa de la municipalidad del reporte (US-028).

    Existe porque ``procesar`` la exige: la asignación **es** la transición, así
    que todo test que ponga un reporte En proceso necesita un área de su propio
    municipio. Una de otra municipalidad se rechaza, que es justamente lo que
    comprueban los tests que no usan este atajo.
    """
    return OperationalAreaFactory.create(municipality=report.municipality)


class OfficialResponseFactory(DjangoModelFactory[OfficialResponse]):
    """Respuesta oficial ya publicada (US-024)."""

    report = factory.SubFactory(ReportFactory)
    author = factory.SubFactory(UserFactory)
    municipality = factory.LazyAttribute(lambda o: o.report.municipality)
    text = factory.Faker("sentence", nb_words=12)

    class Meta:
        model = OfficialResponse


class ResolutionEvidenceFactory(DjangoModelFactory[ResolutionEvidence]):
    """Parte de trabajo de un cierre ya registrado (US-046)."""

    report = factory.SubFactory(ReportFactory)
    photo = ImageField(filename="resolution.jpg")
    description = factory.Faker("sentence", nb_words=12)
    operator = factory.SubFactory(OperatorFactory)
    operational_area = factory.LazyAttribute(lambda o: o.operator.operational_area)
    latitude = factory.LazyAttribute(lambda o: o.report.latitude)
    longitude = factory.LazyAttribute(lambda o: o.report.longitude)

    class Meta:
        model = ResolutionEvidence


class ResolutionAppealFactory(DjangoModelFactory[ResolutionAppeal]):
    """Apelación del autor a un cierre (US-048)."""

    report = factory.SubFactory(ReportFactory)
    author = factory.LazyAttribute(lambda o: o.report.author)
    reason = factory.Faker("sentence", nb_words=10)
    photo = ImageField(filename="appeal.jpg")

    class Meta:
        model = ResolutionAppeal
