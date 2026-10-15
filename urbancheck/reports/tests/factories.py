from __future__ import annotations

import factory
from factory.django import DjangoModelFactory
from factory.django import ImageField

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionComparison
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory


class ReportFactory(DjangoModelFactory[Report]):
    author = factory.SubFactory(UserFactory)
    municipality = factory.SubFactory(MunicipalityFactory)
    # Ya difuminada (US-042): un reporte de factory es un reporte **publicado**.
    # Sin esto la mitad de la suite dejaría de ver sus propios reportes en el
    # feed, y además el constraint rechazaría la fila por tener foto sin
    # procesar. Un reporte en procesamiento se arma explícitamente.
    photo = ImageField(filename="report.jpg")
    photo_status = PhotoStatus.PROCESADA
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
    photo_status = PhotoStatus.PROCESADA
    description = factory.Faker("sentence", nb_words=12)
    operator = factory.SubFactory(OperatorFactory)
    operational_area = factory.LazyAttribute(lambda o: o.operator.operational_area)
    latitude = factory.LazyAttribute(lambda o: o.report.latitude)
    longitude = factory.LazyAttribute(lambda o: o.report.longitude)

    class Meta:
        model = ResolutionEvidence


class ResolutionComparisonFactory(DjangoModelFactory[ResolutionComparison]):
    """Comparación automática ya terminada de un cierre (US-015)."""

    evidence = factory.SubFactory(ResolutionEvidenceFactory)
    status = ResolutionComparison.Status.COMPLETED
    verdict = ResolutionComparison.Verdict.CONSISTENT
    explanation = "El bache ya no se ve y el asfalto es nuevo."
    model_name = "gemini-test"

    class Meta:
        model = ResolutionComparison


class ResolutionAppealFactory(DjangoModelFactory[ResolutionAppeal]):
    """Apelación del autor a un cierre (US-048)."""

    report = factory.SubFactory(ReportFactory)
    author = factory.LazyAttribute(lambda o: o.report.author)
    reason = factory.Faker("sentence", nb_words=10)
    photo = ImageField(filename="appeal.jpg")
    photo_status = PhotoStatus.PROCESADA

    class Meta:
        model = ResolutionAppeal


class ReportComplaintFactory(DjangoModelFactory[ReportComplaint]):
    """Solicitud por dato personal visible, todavía pendiente (US-043).

    ``image_name`` se toma del archivo que se publica en ese momento, igual que
    al registrarla desde la API. Con un motivo de contenido (US-021) queda
    vacío: esas denuncias apuntan al reporte y no a un archivo.
    """

    report = factory.SubFactory(ReportFactory)
    resolution_evidence = None
    reporter = factory.SubFactory(UserFactory)
    reason = ReportComplaint.Reason.DATO_PERSONAL
    image_name = factory.LazyAttribute(
        lambda o: (
            (o.resolution_evidence or o.report).photo.name
            if o.reason in ReportComplaint.PLATFORM_REASONS
            else ""
        ),
    )

    class Meta:
        model = ReportComplaint
