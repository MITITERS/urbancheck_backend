"""US-042 — el circuito de difuminado: reintentos, fallo definitivo y aviso.

Escenarios 1, 4, 5 y 8. Qué se ve y qué no mientras tanto se prueba en
``reports/tests/test_photo_processing_visibility.py``.

El detector real no se usa acá: lo que se ejercita es la política —cuántas
veces se reintenta, qué se reintenta y qué no, y en qué estado queda la cosa
cuando se agota—, no la calidad del difuminado, que es de US-041.
"""

from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path

import pytest
from celery.exceptions import Retry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.anonymization import pipeline
from urbancheck.anonymization import service
from urbancheck.anonymization.models import PhotoStatus
from urbancheck.anonymization.storage import pending_photo_storage
from urbancheck.anonymization.tasks import anonymize_photo
from urbancheck.anonymization.tasks import requeue_stale_pending_photos
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.notifications.models import Notification
from urbancheck.reports.models import Report
from urbancheck.reports.models import ResolutionComparison
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201

HERE = {"latitude": "-32.410300", "longitude": "-63.240000"}

REPORT_LABEL = "reports.report"


def an_image() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 60), color=(120, 130, 140)).save(buffer, format="JPEG")
    return buffer.getvalue()


def upload() -> SimpleUploadedFile:
    return SimpleUploadedFile("foto.jpg", an_image(), content_type="image/jpeg")


def pending_files() -> set[Path]:
    root = Path(pending_photo_storage().location)
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_file()}


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def author_client(author) -> APIClient:
    return client_for(author)


@pytest.fixture
def queued(author_client) -> Report:
    """Un reporte recién creado por la API, con la foto en cola."""
    response = author_client.post(
        "/api/reports/",
        {
            "photo": upload(),
            "description": "Bache frente a la escuela.",
            "category": "bache",
            **HERE,
        },
        format="multipart",
    )
    assert response.status_code == HTTP_CREATED
    return Report.objects.get(pk=response.data["id"])


class BrokenDetector:
    """Un detector que siempre falla, como si el ONNX no cargara."""

    def detect(self, bgr):
        msg = "onnxruntime error"
        raise RuntimeError(msg)


def run_task(instance, **kwargs):
    return anonymize_photo.apply(
        args=[instance._meta.label_lower, instance.pk],  # noqa: SLF001
        **kwargs,
    )


class TestSuccess:
    """Escenario 1: el reporte se publica cuando el difuminado termina."""

    def test_the_endpoint_answers_before_processing(self, queued):
        """CP-042-01 (US-042 E1)."""
        assert queued.photo_is_processing
        assert queued.photo_pending
        assert not queued.photo

    def test_processing_publishes_it_and_discards_the_original(
        self,
        queued,
        django_capture_on_commit_callbacks,
    ):
        """CP-041-19 (US-041 E6) · CP-042-02 (US-042 E1)."""
        with django_capture_on_commit_callbacks(execute=True):
            run_task(queued)

        queued.refresh_from_db()
        assert queued.photo_is_ready
        assert queued.photo
        assert queued.photo_attempts == 1
        # La original no se conserva "por las dudas".
        assert not queued.photo_pending
        assert pending_files() == set()

    def test_running_it_twice_changes_nothing(
        self,
        queued,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-38 (US-042 Robustez).

        Un broker puede entregar el mismo mensaje dos veces.

        La segunda vez la original ya no está, así que sin la guarda de
        idempotencia el reporte publicado terminaría marcado como fallido.
        """
        with django_capture_on_commit_callbacks(execute=True):
            run_task(queued)
        queued.refresh_from_db()
        published = queued.photo.name

        with django_capture_on_commit_callbacks(execute=True):
            run_task(queued)

        queued.refresh_from_db()
        assert queued.photo_is_ready
        assert queued.photo.name == published
        assert queued.photo_attempts == 1


class TestRetries:
    """Escenario 4: se reintenta lo transitorio, con espera creciente."""

    def test_a_detector_failure_is_retried_with_growing_backoff(
        self,
        queued,
        monkeypatch,
        settings,
    ):
        """CP-042-12 (US-042 E4)."""
        settings.ANONYMIZATION_MAX_RETRIES = 3
        settings.ANONYMIZATION_RETRY_BASE_SECONDS = 30
        monkeypatch.setattr(service, "_face_detector", BrokenDetector)

        countdowns = []

        def capture(*, exc, countdown, max_retries):
            countdowns.append(countdown)
            raise Retry

        monkeypatch.setattr(anonymize_photo, "retry", capture)

        for attempt in range(3):
            anonymize_photo.push_request(retries=attempt)
            try:
                with pytest.raises(Retry):
                    anonymize_photo.run(REPORT_LABEL, queued.pk)
            finally:
                anonymize_photo.pop_request()

        assert countdowns == [30, 60, 120]

    def test_the_maximum_comes_from_configuration(
        self,
        queued,
        monkeypatch,
        settings,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-13 (US-042 E4).

        Nada de números mágicos: bajar el tope cambia el comportamiento.
        """
        settings.ANONYMIZATION_MAX_RETRIES = 0
        monkeypatch.setattr(service, "_face_detector", BrokenDetector)

        with django_capture_on_commit_callbacks(execute=True):
            run_task(queued)

        queued.refresh_from_db()
        assert queued.photo_has_failed

    def test_a_broken_file_is_not_retried_even_once(
        self,
        author_client,
        monkeypatch,
        settings,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-14 (US-042 E4).

        Reintentar algo que no se puede abrir da siempre lo mismo.

        Se falla de una y el ciudadano se entera ahora, en lugar de esperar los
        reintentos completos para recibir la misma respuesta.
        """
        settings.ANONYMIZATION_MAX_RETRIES = 5
        report = ReportFactory.create(photo="", photo_status=PhotoStatus.PENDIENTE)
        report.photo_pending.save("roto.jpg", SimpleUploadedFile("roto.jpg", b"xx"))

        retries = []
        monkeypatch.setattr(
            anonymize_photo,
            "retry",
            lambda **kwargs: retries.append(kwargs),
        )

        with django_capture_on_commit_callbacks(execute=True):
            run_task(report)

        report.refresh_from_db()
        assert retries == []
        assert report.photo_has_failed


class TestDefinitiveFailure:
    """Escenario 5: no se publica, se avisa al autor y queda registrado."""

    @pytest.fixture
    def failed(self, queued, monkeypatch, settings, django_capture_on_commit_callbacks):
        settings.ANONYMIZATION_MAX_RETRIES = 0
        monkeypatch.setattr(service, "_face_detector", BrokenDetector)
        with django_capture_on_commit_callbacks(execute=True):
            run_task(queued)
        queued.refresh_from_db()
        return queued

    def test_it_is_marked_and_dated(self, failed):
        """CP-042-15 (US-042 E5)."""
        assert failed.photo_has_failed
        assert failed.photo_failed_at is not None

    def test_nothing_is_published_and_the_original_is_gone(self, failed):
        """CP-042-16 (US-042 E5)."""
        assert not failed.photo
        assert not failed.photo_pending
        assert pending_files() == set()

    def test_the_author_is_told_they_can_upload_it_again(self, failed, author):
        """CP-042-17 (US-042 E5)."""
        notification = Notification.objects.get(
            recipient=author,
            kind=Notification.Kind.IMAGEN_NO_PROCESADA,
        )

        assert notification.report_id == failed.pk
        assert "volvé a cargarlo" in notification.message.lower()

    def test_it_is_logged_with_its_code_and_without_the_filename(
        self,
        queued,
        monkeypatch,
        settings,
        caplog,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-18 (US-042 E5)."""
        settings.ANONYMIZATION_MAX_RETRIES = 0
        monkeypatch.setattr(service, "_face_detector", BrokenDetector)
        original_name = queued.photo_pending.name

        with caplog.at_level("WARNING"), django_capture_on_commit_callbacks(
            execute=True,
        ):
            run_task(queued)

        record = next(r for r in caplog.records if "anonimizar" in r.getMessage())
        assert "detector_unavailable" in record.getMessage()
        assert original_name not in record.getMessage()

    def test_the_author_can_upload_another_photo_and_it_is_queued_again(
        self,
        failed,
        author_client,
    ):
        """CP-042-19 (US-042 E5)."""
        response = author_client.patch(
            f"/api/reports/{failed.pk}/",
            {"photo": upload()},
            format="multipart",
        )

        assert response.status_code == HTTP_OK
        failed.refresh_from_db()
        assert failed.photo_is_processing
        assert failed.photo_attempts == 0
        assert failed.photo_failed_at is None
        assert failed.photo_pending


class TestTheOperatorClosing:
    """Escenario 8: la foto del cierre atraviesa el mismo circuito."""

    @pytest.fixture
    def area(self, active_municipality):
        return OperationalAreaFactory.create(municipality=active_municipality)

    @pytest.fixture
    def operator(self, area):
        return OperatorFactory.create(operational_area=area)

    @pytest.fixture
    def in_progress(self, area, author):
        return ReportFactory.create(
            author=author,
            municipality=area.municipality,
            operational_area=area,
            status=Report.Status.EN_PROCESO,
            area_assigned_at=timezone.now(),
            **HERE,
        )

    def close(self, operator, report):
        return client_for(operator).post(
            f"/api/operator/reports/{report.pk}/resolve/",
            {"photo": upload(), "description": "Se rellenó el bache.", **HERE},
            format="multipart",
        )

    def test_the_evidence_is_registered_without_its_photo(
        self,
        operator,
        in_progress,
    ):
        """CP-042-29 (US-042 E8)."""
        assert self.close(operator, in_progress).status_code == HTTP_OK

        evidence = ResolutionEvidence.objects.get(report=in_progress)
        assert evidence.photo_is_processing
        assert not evidence.photo
        assert evidence.description
        # El cierre sí ocurrió: la publicación diferida es de la imagen.
        in_progress.refresh_from_db()
        assert in_progress.status == Report.Status.RESUELTO_PENDIENTE

    def test_the_citizen_does_not_see_the_photo_while_it_processes(
        self,
        operator,
        in_progress,
        author_client,
    ):
        """CP-042-30 (US-042 E8)."""
        self.close(operator, in_progress)

        evidence = author_client.get(f"/api/reports/{in_progress.pk}/").data[
            "resolution_evidences"
        ][0]

        assert evidence["photo"] is None
        assert evidence["photo_status"] == PhotoStatus.PENDIENTE

    def test_a_failed_close_photo_leaves_the_close_standing(
        self,
        operator,
        in_progress,
        monkeypatch,
        settings,
        django_capture_on_commit_callbacks,
    ):
        """CP-042-31 (US-042 E8).

        El cierre ya ocurrió y el ciudadano ya fue avisado.

        Revertirlo ahora abriría un caso que la historia no plantea. Queda un
        parte de trabajo con descripción y sin imagen, y el operario se entera.
        """
        settings.ANONYMIZATION_MAX_RETRIES = 0
        self.close(operator, in_progress)
        evidence = ResolutionEvidence.objects.get(report=in_progress)
        monkeypatch.setattr(service, "_face_detector", BrokenDetector)

        with django_capture_on_commit_callbacks(execute=True):
            run_task(evidence)

        evidence.refresh_from_db()
        in_progress.refresh_from_db()
        assert evidence.photo_has_failed
        assert in_progress.status == Report.Status.RESUELTO_PENDIENTE
        assert ResolutionComparison.objects.get(
            evidence=evidence,
        ).status == ResolutionComparison.Status.UNAVAILABLE
        assert Notification.objects.filter(
            recipient=operator,
            kind=Notification.Kind.IMAGEN_NO_PROCESADA,
        ).exists()


class TestNothingStaysQueuedForever:
    """El seguro contra el mensaje que el broker nunca entregó."""

    def test_a_stale_photo_is_requeued(self, queued, settings, monkeypatch):
        """CP-042-39 (US-042 Robustez)."""
        settings.ANONYMIZATION_STALE_MINUTES = 30
        # Se mide desde que entró a la cola, no desde que se creó el reporte:
        # una foto reemplazada hoy sobre un reporte viejo no está vencida.
        Report.objects.filter(pk=queued.pk).update(
            photo_queued_at=timezone.now() - timedelta(hours=2),
        )
        sent = []
        monkeypatch.setattr(
            anonymize_photo,
            "delay",
            lambda *args, **kwargs: sent.append(args),
        )

        result = requeue_stale_pending_photos()

        assert result == {"requeued": 1}
        assert sent == [(REPORT_LABEL, queued.pk)]

    def test_a_recent_one_is_left_alone(self, queued, settings, monkeypatch):
        """CP-042-40 (US-042 Robustez)."""
        settings.ANONYMIZATION_STALE_MINUTES = 30
        sent = []
        monkeypatch.setattr(
            anonymize_photo,
            "delay",
            lambda *args, **kwargs: sent.append(args),
        )

        assert requeue_stale_pending_photos() == {"requeued": 0}
        assert sent == []


class TestADeletedReportIsNotAnError:
    def test_the_task_tolerates_a_report_that_no_longer_exists(self, queued):
        """CP-042-41 (US-042 Robustez)."""
        pk = queued.pk
        Report.objects.filter(pk=pk).delete()

        # No levanta, y no deja nada marcado como fallido.
        anonymize_photo.apply(args=[REPORT_LABEL, pk])

        assert not Report.objects.filter(pk=pk).exists()


class TestTheOriginalIsNotReachable:
    def test_the_pending_photo_has_no_url(self, queued):
        """CP-041-24 (US-041 E7).

        Exponer el campo por descuido falla en vez de filtrar la original.
        """
        with pytest.raises(ValueError, match="not accessible via a URL"):
            _ = queued.photo_pending.url

    def test_the_pending_photo_lives_outside_the_served_media_root(
        self,
        queued,
        settings,
    ):
        """CP-041-25 (US-041 E7)."""
        pending = Path(pending_photo_storage().path(queued.photo_pending.name))

        assert pending.is_file()
        assert Path(settings.MEDIA_ROOT) not in pending.parents


def test_the_pipeline_never_leaves_a_photo_pending_forever(
    queued,
    monkeypatch,
    settings,
):
    """CP-042-42 (US-042 Robustez).

    Toda rama termina en `procesada` o en `fallida`, nunca en el medio.
    """
    settings.ANONYMIZATION_MAX_RETRIES = 0

    def explode(*args, **kwargs):
        msg = "algo que nadie previó"
        raise TypeError(msg)

    monkeypatch.setattr(pipeline, "anonymize", explode)

    anonymize_photo.apply(args=[REPORT_LABEL, queued.pk])

    queued.refresh_from_db()
    assert queued.photo_status in {PhotoStatus.PROCESADA, PhotoStatus.FALLIDA}
