"""US-021 — denunciar un reporte."""

from __future__ import annotations

import json

import pytest
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.reports.complaints import reason_catalog
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportComplaintFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

Reason = ReportComplaint.Reason
Recipient = ReportComplaint.Recipient

CONTENT_REASONS = [Reason.CONTENIDO_INAPROPIADO, Reason.REPORTE_FALSO]
# Muchas más que las tres que tumbaban un reporte en la versión anterior.
MANY_COMPLAINTS = 12


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def file(client, report, **payload):
    return client.post(
        f"/api/reports/{report.pk}/complaints/",
        payload,
        format="json",
    )


def listed_ids(response) -> set[int]:
    data = response.data
    rows = data["results"] if isinstance(data, dict) else data
    return {row["id"] for row in rows}


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def neighbour():
    return UserFactory.create()


@pytest.fixture
def report(active_municipality, author):
    return ReportFactory.create(
        author=author,
        municipality=active_municipality,
        status=Report.Status.REPORTADO,
    )


class TestFilingAComplaint:
    """Escenario 1: usuario, motivo, comentario opcional y fecha."""

    @pytest.mark.parametrize("reason", list(Reason))
    def test_it_is_registered_for_every_reason(self, report, neighbour, reason):
        before = timezone.now()

        response = file(
            client_for(neighbour),
            report,
            reason=reason,
            comment="No hay nada en esa esquina.",
        )

        assert response.status_code == HTTP_CREATED
        complaint = ReportComplaint.objects.get()
        assert complaint.report == report
        assert complaint.reporter == neighbour
        assert complaint.reason == reason
        assert complaint.comment == "No hay nada en esa esquina."
        assert complaint.created_at >= before
        assert complaint.is_pending

    def test_the_comment_is_optional(self, report, neighbour):
        response = file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)

        assert response.status_code == HTTP_CREATED
        assert ReportComplaint.objects.get().comment == ""

    def test_a_comment_that_is_too_long_is_rejected(self, report, neighbour):
        response = file(
            client_for(neighbour),
            report,
            reason=Reason.REPORTE_FALSO,
            comment="x" * 501,
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert "comment" in response.data
        assert not ReportComplaint.objects.exists()

    @pytest.mark.parametrize("reason", CONTENT_REASONS)
    def test_a_content_complaint_is_confirmed_as_going_to_the_municipality(
        self,
        report,
        neighbour,
        reason,
    ):
        response = file(client_for(neighbour), report, reason=reason)

        assert "municipio" in response.data["detail"]
        assert "24 horas" not in response.data["detail"]

    def test_a_personal_data_complaint_is_confirmed_with_the_rn12_deadline(
        self,
        report,
        neighbour,
    ):
        response = file(client_for(neighbour), report, reason=Reason.DATO_PERSONAL)

        assert "24 horas" in response.data["detail"]

    def test_a_content_complaint_points_at_the_report_not_at_an_image(
        self,
        report,
        neighbour,
    ):
        file(client_for(neighbour), report, reason=Reason.CONTENIDO_INAPROPIADO)

        complaint = ReportComplaint.objects.get()
        assert complaint.image_name == ""
        assert complaint.resolution_evidence is None

    @pytest.mark.parametrize("factory", [ValidatorFactory, MunicipalAgentFactory])
    def test_work_accounts_use_their_personal_account(self, report, factory):
        worker = factory.create(municipality=report.municipality)

        response = file(client_for(worker), report, reason=Reason.REPORTE_FALSO)

        assert response.status_code == HTTP_FORBIDDEN
        assert not ReportComplaint.objects.exists()

    def test_the_operator_is_rejected(self, report):
        response = file(
            client_for(OperatorFactory.create()),
            report,
            reason=Reason.REPORTE_FALSO,
        )

        assert response.status_code == HTTP_FORBIDDEN

    def test_a_report_that_does_not_exist_answers_404(self, neighbour):
        response = client_for(neighbour).post(
            "/api/reports/999999/complaints/",
            {"reason": Reason.REPORTE_FALSO},
            format="json",
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestReasonCatalog:
    """Escenario 2: los tres motivos, declarados en un único lugar."""

    def test_it_offers_the_three_reasons(self, neighbour):
        response = client_for(neighbour).get("/api/reports/complaint-reasons/")

        assert response.status_code == HTTP_OK
        assert [(row["value"], row["label"]) for row in response.data] == [
            ("contenido_inapropiado", "Contenido inapropiado u ofensivo"),
            ("reporte_falso", "Reporte falso o inexistente"),
            ("dato_personal", "Dato personal visible"),
        ]

    def test_each_reason_carries_its_recipient(self, neighbour):
        response = client_for(neighbour).get("/api/reports/complaint-reasons/")

        assert {row["value"]: row["recipient"] for row in response.data} == {
            "contenido_inapropiado": "agente_municipal",
            "reporte_falso": "agente_municipal",
            "dato_personal": "admin_plataforma",
        }

    def test_every_reason_has_a_recipient(self):
        """Un motivo nuevo que no se sume al catálogo no puede pasar inadvertido."""
        assert set(ReportComplaint.REASON_RECIPIENTS) == set(Reason)
        assert len(reason_catalog()) == len(Reason)

    def test_it_requires_a_session(self):
        response = APIClient().get("/api/reports/complaint-reasons/")

        assert response.status_code in {401, 403}


class TestRouting:
    """Escenario 3: el destinatario sale del motivo."""

    @pytest.mark.parametrize("reason", CONTENT_REASONS)
    def test_content_complaints_go_to_the_municipal_agent(
        self,
        report,
        neighbour,
        reason,
    ):
        response = file(client_for(neighbour), report, reason=reason)

        complaint = ReportComplaint.objects.get()
        assert response.data["recipient"] == Recipient.AGENTE_MUNICIPAL
        assert complaint.recipient == Recipient.AGENTE_MUNICIPAL
        assert list(ReportComplaint.objects.for_municipal_review()) == [complaint]
        assert not ReportComplaint.objects.for_platform_review().exists()

    def test_personal_data_complaints_go_to_the_platform_admin(
        self,
        report,
        neighbour,
    ):
        response = file(client_for(neighbour), report, reason=Reason.DATO_PERSONAL)

        complaint = ReportComplaint.objects.get()
        assert response.data["recipient"] == Recipient.ADMIN_PLATAFORMA
        assert complaint.recipient == Recipient.ADMIN_PLATAFORMA
        assert list(ReportComplaint.objects.for_platform_review()) == [complaint]
        assert not ReportComplaint.objects.for_municipal_review().exists()

    def test_the_municipal_queue_is_the_one_of_the_reports_jurisdiction(
        self,
        report,
        neighbour,
    ):
        file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)

        complaint = ReportComplaint.objects.for_municipal_review().get()
        assert complaint.report.municipality == report.municipality

    def test_a_personal_data_complaint_enters_the_us043_circuit(
        self,
        report,
        neighbour,
    ):
        """Es el único motivo con efecto inmediato, y lo produce US-043."""
        file(client_for(neighbour), report, reason=Reason.DATO_PERSONAL)

        complaint = ReportComplaint.objects.get()
        assert complaint.image_name == report.photo.name
        viewer = client_for(UserFactory.create())
        assert report.pk not in listed_ids(viewer.get("/api/reports/"))


class TestReasonIsRequired:
    """Escenario 4."""

    @pytest.mark.parametrize(
        "payload",
        [{}, {"reason": ""}, {"reason": None}, {"comment": "Sin motivo"}],
    )
    def test_a_complaint_without_a_reason_is_rejected(
        self,
        report,
        neighbour,
        payload,
    ):
        response = file(client_for(neighbour), report, **payload)

        assert response.status_code == HTTP_BAD_REQUEST
        assert [str(error) for error in response.data["reason"]] == [
            "El motivo es obligatorio.",
        ]
        assert not ReportComplaint.objects.exists()

    def test_a_reason_outside_the_catalog_is_rejected(self, report, neighbour):
        response = file(client_for(neighbour), report, reason="spam")

        assert response.status_code == HTTP_BAD_REQUEST
        assert "reason" in response.data
        assert not ReportComplaint.objects.exists()


class TestNoAutomaticHiding:
    """Escenario 5: ningún umbral de denuncias toca el reporte."""

    @pytest.fixture
    def flooded_report(self, report):
        for reason in CONTENT_REASONS:
            for _ in range(MANY_COMPLAINTS):
                response = file(
                    client_for(UserFactory.create()),
                    report,
                    reason=reason,
                )
                assert response.status_code == HTTP_CREATED
        return report

    def test_it_stays_in_the_feed(self, flooded_report):
        response = client_for(UserFactory.create()).get("/api/reports/")

        assert flooded_report.pk in listed_ids(response)

    def test_it_stays_on_the_map(self, flooded_report):
        response = client_for(UserFactory.create()).get("/api/reports/map/")

        assert flooded_report.pk in listed_ids(response)

    def test_it_can_still_be_opened_by_id(self, flooded_report):
        response = client_for(UserFactory.create()).get(
            f"/api/reports/{flooded_report.pk}/",
        )

        assert response.status_code == HTTP_OK

    def test_its_status_does_not_change(self, flooded_report):
        history_before = ReportStatusHistory.objects.filter(
            report=flooded_report,
        ).count()

        flooded_report.refresh_from_db()

        assert flooded_report.status == Report.Status.REPORTADO
        assert (
            ReportStatusHistory.objects.filter(report=flooded_report).count()
            == history_before
        )

    def test_it_is_not_marked_as_under_review(self, flooded_report):
        response = client_for(flooded_report.author).get(
            f"/api/reports/{flooded_report.pk}/",
        )

        assert response.data["under_privacy_review"] is False

    def test_the_visibility_function_ignores_content_complaints(
        self,
        flooded_report,
    ):
        assert Report.objects.publicly_visible().filter(pk=flooded_report.pk).exists()


class TestDuplicateComplaint:
    """Escenario 6: una por persona, reporte y motivo."""

    @pytest.mark.parametrize("reason", list(Reason))
    def test_the_same_reason_twice_creates_no_new_record(
        self,
        report,
        neighbour,
        reason,
    ):
        client = client_for(neighbour)
        file(client, report, reason=reason)

        response = file(client, report, reason=reason)

        assert response.status_code == HTTP_CONFLICT
        assert response.data["code"] == "complaint_already_filed"
        assert ReportComplaint.objects.count() == 1

    def test_the_same_user_can_file_a_different_reason(self, report, neighbour):
        client = client_for(neighbour)
        file(client, report, reason=Reason.REPORTE_FALSO)

        response = file(client, report, reason=Reason.CONTENIDO_INAPROPIADO)

        assert response.status_code == HTTP_CREATED
        assert ReportComplaint.objects.count() == len(CONTENT_REASONS)

    def test_another_user_can_file_the_same_reason(self, report, neighbour):
        file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)

        response = file(
            client_for(UserFactory.create()),
            report,
            reason=Reason.REPORTE_FALSO,
        )

        assert response.status_code == HTTP_CREATED

    def test_the_same_user_can_file_the_same_reason_on_another_report(
        self,
        report,
        neighbour,
        active_municipality,
    ):
        other = ReportFactory.create(
            municipality=active_municipality,
            status=Report.Status.REPORTADO,
        )
        client = client_for(neighbour)
        file(client, report, reason=Reason.REPORTE_FALSO)

        response = file(client, other, reason=Reason.REPORTE_FALSO)

        assert response.status_code == HTTP_CREATED

    def test_a_resolved_content_complaint_still_blocks_a_new_one(
        self,
        report,
        neighbour,
    ):
        ReportComplaintFactory.create(
            report=report,
            reporter=neighbour,
            reason=Reason.REPORTE_FALSO,
            status=ReportComplaint.Status.DESESTIMADA,
        )

        response = file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)

        assert response.status_code == HTTP_CONFLICT

    def test_the_database_enforces_it(self, report, neighbour):
        ReportComplaintFactory.create(
            report=report,
            reporter=neighbour,
            reason=Reason.REPORTE_FALSO,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            ReportComplaintFactory.create(
                report=report,
                reporter=neighbour,
                reason=Reason.REPORTE_FALSO,
            )


class TestOwnReport:
    """Escenario 7."""

    @pytest.mark.parametrize("reason", list(Reason))
    def test_the_author_cannot_file_a_complaint_on_their_own_report(
        self,
        report,
        author,
        reason,
    ):
        response = file(client_for(author), report, reason=reason)

        assert response.status_code == HTTP_FORBIDDEN
        assert not ReportComplaint.objects.exists()


class TestFinalStatus:
    """Escenario 8: lo que ya no es público no se denuncia."""

    @pytest.mark.parametrize(
        "final_status",
        [Report.Status.CANCELADO, Report.Status.ARCHIVADO],
    )
    @pytest.mark.parametrize("reason", list(Reason))
    def test_a_cancelled_or_archived_report_cannot_be_reported(
        self,
        active_municipality,
        neighbour,
        final_status,
        reason,
    ):
        report = ReportFactory.create(
            municipality=active_municipality,
            status=final_status,
        )

        response = file(client_for(neighbour), report, reason=reason)

        assert response.status_code == HTTP_CONFLICT
        assert response.data["code"] == "report_not_public"
        assert not ReportComplaint.objects.exists()

    def test_a_report_withdrawn_for_personal_data_cannot_be_reported(
        self,
        report,
        neighbour,
    ):
        Report.objects.filter(pk=report.pk).update(photo_removed_at=timezone.now())

        response = file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)

        assert response.status_code == HTTP_CONFLICT
        assert response.data["code"] == "report_not_public"

    @pytest.mark.parametrize(
        "active_status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
            Report.Status.EN_PROCESO,
            Report.Status.RESUELTO,
        ],
    )
    def test_a_published_report_can_be_reported(
        self,
        active_municipality,
        neighbour,
        active_status,
    ):
        report = ReportFactory.create(
            municipality=active_municipality,
            status=active_status,
        )

        response = file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)

        assert response.status_code == HTTP_CREATED


class TestAnonymity:
    """Escenario 9: el autor no sabe quién lo denunció ni cuántas veces."""

    COMMENT = "comentario-que-solo-lee-quien-resuelve"

    @pytest.fixture
    def reporter(self):
        return UserFactory.create(name="Denunciante Reservado")

    @pytest.fixture
    def reported(self, report, reporter):
        for reason in CONTENT_REASONS:
            file(client_for(reporter), report, reason=reason, comment=self.COMMENT)
        return report

    @pytest.mark.parametrize(
        "path",
        [
            "/api/reports/{pk}/",
            "/api/reports/",
            "/api/reports/?mine=true",
            "/api/reports/map/",
            "/api/reports/{pk}/comments/",
        ],
    )
    @pytest.mark.parametrize("viewer", ["author", "third_party"])
    def test_no_public_serializer_carries_the_complaint(
        self,
        reported,
        reporter,
        path,
        viewer,
    ):
        user = reported.author if viewer == "author" else UserFactory.create()

        response = client_for(user).get(path.format(pk=reported.pk))

        assert response.status_code == HTTP_OK
        body = json.dumps(response.json())
        assert reporter.name not in body
        assert reporter.email not in body
        assert self.COMMENT not in body
        assert "complaint" not in body
        assert "denuncia" not in body.lower()

    def test_the_author_is_not_told_how_many_complaints_there_are(self, reported):
        response = client_for(reported.author).get(f"/api/reports/{reported.pk}/")

        assert not [key for key in response.data if "complaint" in key]
        assert response.data["under_privacy_review"] is False

    def test_the_authors_notice_names_nobody(self, reported, reporter):
        notice = Notification.objects.get(recipient=reported.author)

        assert notice.actor is None
        assert reporter.name not in notice.message
        assert self.COMMENT not in notice.message

    def test_the_notifications_api_does_not_expose_the_reporter(
        self,
        reported,
        reporter,
    ):
        response = client_for(reported.author).get("/api/notifications/")

        assert response.status_code == HTTP_OK
        body = json.dumps(response.json())
        assert "reporte_denunciado" in body
        assert reporter.name not in body
        assert reporter.email not in body
        assert self.COMMENT not in body

    def test_the_receipt_does_not_carry_the_reporter(self, report, reporter):
        response = file(client_for(reporter), report, reason=Reason.REPORTE_FALSO)

        assert "reporter" not in response.data


def notices(user, kind) -> list[Notification]:
    return list(Notification.objects.filter(recipient=user, kind=kind))


class TestNotifications:
    """Las dos partes se enteran: quien denuncia y el autor del reporte."""

    @pytest.mark.parametrize("reason", list(Reason))
    def test_the_reporter_gets_the_receipt_as_a_notice(
        self,
        report,
        neighbour,
        reason,
    ):
        response = file(client_for(neighbour), report, reason=reason)

        (notice,) = notices(neighbour, Notification.Kind.DENUNCIA_RECIBIDA)
        assert notice.report == report
        assert notice.message == response.data["detail"]

    @pytest.mark.parametrize("reason", CONTENT_REASONS)
    def test_the_author_learns_the_report_was_reported(
        self,
        report,
        neighbour,
        reason,
    ):
        file(client_for(neighbour), report, reason=reason)

        (notice,) = notices(report.author, Notification.Kind.REPORTE_DENUNCIADO)
        assert notice.report == report
        assert notice.actor is None
        assert "sigue publicado" in notice.message

    def test_the_author_is_told_once_however_many_complaints_arrive(self, report):
        """Uno por denuncia le diría cuántas hay (escenario 9)."""
        for reason in CONTENT_REASONS:
            for _ in range(3):
                file(client_for(UserFactory.create()), report, reason=reason)

        assert len(notices(report.author, Notification.Kind.REPORTE_DENUNCIADO)) == 1

    def test_the_author_is_told_again_once_the_previous_ones_were_resolved(
        self,
        report,
        neighbour,
    ):
        file(client_for(neighbour), report, reason=Reason.REPORTE_FALSO)
        ReportComplaint.objects.update(status=ReportComplaint.Status.DESESTIMADA)

        file(client_for(UserFactory.create()), report, reason=Reason.REPORTE_FALSO)

        expected = 2
        assert (
            len(notices(report.author, Notification.Kind.REPORTE_DENUNCIADO))
            == expected
        )

    def test_a_personal_data_complaint_tells_the_author_through_us043(
        self,
        report,
        neighbour,
    ):
        """Un solo aviso al autor, y es el que le explica el ocultamiento."""
        file(client_for(neighbour), report, reason=Reason.DATO_PERSONAL)

        kinds = set(
            Notification.objects.filter(recipient=report.author).values_list(
                "kind",
                flat=True,
            ),
        )
        assert kinds == {Notification.Kind.REPORTE_EN_REVISION}

    @pytest.mark.parametrize(
        "payload",
        [{}, {"reason": "spam"}],
    )
    def test_a_rejected_complaint_notifies_nobody(self, report, neighbour, payload):
        file(client_for(neighbour), report, **payload)

        assert not Notification.objects.exists()

    def test_a_duplicate_does_not_notify_again(self, report, neighbour):
        client = client_for(neighbour)
        file(client, report, reason=Reason.REPORTE_FALSO)
        before = Notification.objects.count()

        file(client, report, reason=Reason.REPORTE_FALSO)

        assert Notification.objects.count() == before


class TestAuthentication:
    """Escenario 10."""

    @pytest.mark.parametrize("reason", list(Reason))
    def test_an_anonymous_visitor_is_denied(self, report, reason):
        response = file(APIClient(), report, reason=reason)

        assert response.status_code in {401, 403}
        assert not ReportComplaint.objects.exists()
