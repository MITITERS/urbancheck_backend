"""US-049 — el agente municipal resuelve las denuncias por contenido.

Cada contrapeso de la facultad municipal de descartar reportes tiene acá su
test: el motivo público, la apelación al administrador, la reversión y el
registro con origen propio en el historial.
"""

from __future__ import annotations

import importlib
from unittest import mock

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from urbancheck.notifications.models import Notification
from urbancheck.reports.api.panel_serializers import PanelReportDetailSerializer
from urbancheck.reports.models import ModerationDecision
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.state_machine import Origin
from urbancheck.reports.tests.factories import ReportComplaintFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import ResolutionAppealFactory
from urbancheck.reports.tests.factories import area_for
from urbancheck.reports.tests.factories import content_complaint_for
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

INBOX_URL = "/api/panel/moderation/"
APPEALS_URL = "/api/panel/moderation-appeals/"
REASON = "La foto es de otra ciudad: el bache no existe en esa dirección."

Status = Report.Status
CStatus = ReportComplaint.Status


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def rows(response) -> list[dict]:
    data = response.data
    return data["results"] if isinstance(data, dict) else data


@pytest.fixture
def report():
    return ReportFactory.create(status=Status.REPORTADO)


@pytest.fixture
def agent(report):
    return MunicipalAgentFactory.create(municipality=report.municipality)


@pytest.fixture
def admin():
    return PlatformAdminFactory.create()


def discard(agent, report, reason=REASON):
    return client_for(agent).post(
        f"{INBOX_URL}{report.pk}/discard/",
        {"reason": reason},
        format="json",
    )


def dismiss(agent, report, reason=REASON):
    return client_for(agent).post(
        f"{INBOX_URL}{report.pk}/dismiss/",
        {"reason": reason},
        format="json",
    )


def appeal(author, report, reason="El bache existe, está frente a mi casa."):
    return client_for(author).post(
        f"/api/reports/{report.pk}/moderation-appeal/",
        {"reason": reason},
        format="json",
    )


class TestInbox:
    def test_it_lists_pending_content_complaints_of_my_municipality(
        self,
        report,
        agent,
    ):
        """CP-049-01 (US-049 E1). Reporte, motivo, comentario, denunciante y fecha."""
        reporter = UserFactory.create(name="Vecina Denunciante")
        content_complaint_for(report, reporter=reporter, comment="Es falso")

        response = client_for(agent).get(INBOX_URL)

        assert response.status_code == HTTP_OK
        [entry] = rows(response)
        assert entry["id"] == report.pk
        [complaint] = entry["complaints"]
        assert complaint["reason"] == ReportComplaint.Reason.REPORTE_FALSO
        assert complaint["comment"] == "Es falso"
        assert complaint["reporter"]["name"] == "Vecina Denunciante"
        assert complaint["created_at"]

    def test_several_complaints_make_one_entry(self, report, agent):
        """CP-049-02 (US-049 E2). Una entrada por reporte, con la cantidad."""
        for reason in ReportComplaint.Reason.REPORTE_FALSO, "contenido_inapropiado":
            content_complaint_for(report, reason=reason)
        content_complaint_for(report)

        [entry] = rows(client_for(agent).get(INBOX_URL))

        assert entry["pending_complaint_count"] == 3  # noqa: PLR2004
        assert len(entry["complaints"]) == 3  # noqa: PLR2004

    def test_oldest_first(self, agent):
        """CP-049-03 (US-049 E1). Ordenadas por antigüedad."""
        older = ReportFactory.create(municipality=agent.municipality)
        newer = ReportFactory.create(municipality=agent.municipality)
        content_complaint_for(older)
        content_complaint_for(newer)

        ids = [entry["id"] for entry in rows(client_for(agent).get(INBOX_URL))]

        assert ids == [older.pk, newer.pk]

    def test_personal_data_complaints_never_show_up(self, report, agent):
        """CP-049-04 (US-049 E10). Las resuelve el administrador (US-043)."""
        ReportComplaintFactory.create(report=report)  # dato personal

        response = client_for(agent).get(INBOX_URL)

        assert rows(response) == []
        assert client_for(agent).get(f"{INBOX_URL}count/").data == {"pending": 0}

    def test_other_municipalities_do_not_show_up(self, agent):
        """CP-049-05 (US-049 E9)."""
        content_complaint_for(ReportFactory.create())

        assert rows(client_for(agent).get(INBOX_URL)) == []

    def test_the_inbox_filters_by_reason(self, report, agent):
        """CP-049-51. El filtro por tipo de la pantalla de denuncias."""
        content_complaint_for(report, reason=ReportComplaint.Reason.REPORTE_FALSO)
        content_complaint_for(report, reason="contenido_inapropiado")
        other = ReportFactory.create(municipality=agent.municipality)
        content_complaint_for(other, reason="contenido_inapropiado")

        response = client_for(agent).get(f"{INBOX_URL}?reason=reporte_falso")

        [entry] = rows(response)
        assert entry["id"] == report.pk
        # Cuenta y lista solo las de ese motivo.
        assert entry["pending_complaint_count"] == 1
        assert [c["reason"] for c in entry["complaints"]] == ["reporte_falso"]

    def test_the_counter_counts_reports(self, report, agent):
        """CP-049-06. El contador de la navegación cuenta reportes, no denuncias."""
        content_complaint_for(report)
        content_complaint_for(report, reason="contenido_inapropiado")

        response = client_for(agent).get(f"{INBOX_URL}count/")

        assert response.data == {"pending": 1}


class TestResolvedLog:
    """La pestaña «Resueltas» de Denuncias (pedido del usuario del 21/10)."""

    def test_lists_decisions_newest_first_with_their_complaints(self, report, agent):
        """CP-049-52."""
        first = ReportFactory.create(municipality=agent.municipality)
        content_complaint_for(first)
        dismiss(agent, first)
        content_complaint_for(report, reason="contenido_inapropiado")
        discard(agent, report)

        entries = rows(client_for(agent).get(f"{INBOX_URL}resolved/"))

        assert [e["report"]["id"] for e in entries] == [report.pk, first.pk]
        assert entries[0]["outcome"] == "descartado"
        assert entries[0]["reason"] == REASON
        assert entries[0]["decided_by"]["id"] == agent.pk
        assert entries[0]["received_at"]
        assert entries[0]["report"]["photo"]
        assert [c["reason"] for c in entries[0]["complaints"]] == [
            "contenido_inapropiado",
        ]
        assert entries[1]["outcome"] == "desestimado"

    def test_filters_by_reason_and_stays_in_the_jurisdiction(self, report, agent):
        """CP-049-53."""
        content_complaint_for(report, reason="contenido_inapropiado")
        dismiss(agent, report)
        elsewhere = ReportFactory.create()
        content_complaint_for(elsewhere)
        stranger = MunicipalAgentFactory.create(municipality=elsewhere.municipality)
        dismiss(stranger, elsewhere)

        mine = rows(client_for(agent).get(f"{INBOX_URL}resolved/"))
        fake = rows(
            client_for(agent).get(f"{INBOX_URL}resolved/?reason=reporte_falso"),
        )

        assert [e["report"]["id"] for e in mine] == [report.pk]
        assert fake == []

    def test_the_admin_reads_the_chosen_municipality(self, report, agent):
        """CP-049-54."""
        content_complaint_for(report)
        dismiss(agent, report)
        admin = PlatformAdminFactory.create()

        entries = rows(
            client_for(admin).get(
                f"{INBOX_URL}resolved/?municipality={report.municipality_id}",
            ),
        )

        assert [e["report"]["id"] for e in entries] == [report.pk]


class TestDiscard:
    def test_the_report_is_cancelled_and_hidden(self, report, agent):
        """CP-049-07 (US-049 E3)."""
        content_complaint_for(report)

        response = discard(agent, report)

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        assert report.status == Status.CANCELADO
        assert not Report.objects.publicly_visible().filter(pk=report.pk).exists()

    def test_all_complaints_are_resolved_in_one_decision(self, report, agent):
        """CP-049-08 (US-049 E2, E3)."""
        complaints = [
            content_complaint_for(report),
            content_complaint_for(report, reason="contenido_inapropiado"),
        ]

        discard(agent, report)

        decision = ModerationDecision.objects.get(report=report)
        for complaint in complaints:
            complaint.refresh_from_db()
            assert complaint.status == CStatus.REPORTE_DESCARTADO
            assert complaint.moderation_decision == decision
            assert complaint.resolved_by == agent

    def test_the_history_records_the_agent_and_the_origin(self, report, agent):
        """CP-049-09 (US-049 E3). Origen propio, para que US-050 lo distinga."""
        content_complaint_for(report)

        discard(agent, report)

        entry = ReportStatusHistory.objects.get(report=report, status=Status.CANCELADO)
        assert entry.changed_by == agent
        assert entry.origin == Origin.MODERACION_MUNICIPAL
        assert entry.reason == REASON

    def test_the_author_is_notified_with_the_reason(self, report, agent):
        """CP-049-10 (US-049 E3)."""
        content_complaint_for(report)

        discard(agent, report)

        notice = Notification.objects.get(
            recipient=report.author,
            kind=Notification.Kind.CAMBIO_ESTADO,
        )
        assert "descartó" in notice.message
        assert REASON in notice.message

    def test_the_complainants_are_told(self, report, agent):
        """CP-049-11. Quien denunció se entera de que sirvió."""
        complaint = content_complaint_for(report)

        discard(agent, report)

        assert Notification.objects.filter(
            recipient=complaint.reporter,
            kind=Notification.Kind.DENUNCIA_RESUELTA,
        ).exists()

    def test_the_previous_status_is_kept_for_the_reversal(self, agent):
        """CP-049-12 (US-049). No se asume que venía de Reportado."""
        report = ReportFactory.create(
            municipality=agent.municipality,
            status=Status.EN_PROCESO,
        )
        report.operational_area = area_for(report)
        report.save()
        content_complaint_for(report)

        discard(agent, report)

        assert ModerationDecision.objects.get(report=report).previous_status == (
            Status.EN_PROCESO
        )

    def test_it_all_happens_in_one_transaction(self, report, agent):
        """CP-049-13 (US-049 DoD). Si la transición falla, no queda nada."""
        complaint = content_complaint_for(report)

        with (
            mock.patch(
                "urbancheck.reports.moderation.apply_transition",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError),
        ):
            discard(agent, report)

        report.refresh_from_db()
        complaint.refresh_from_db()
        assert report.status == Status.REPORTADO
        assert complaint.status == CStatus.PENDIENTE
        assert not ModerationDecision.objects.exists()

    def test_the_second_decision_gets_a_conflict(self, report, agent):
        """CP-049-14. Dos pestañas: la segunda llega tarde."""
        content_complaint_for(report)
        discard(agent, report)

        response = dismiss(agent, report)

        assert response.status_code == HTTP_CONFLICT

    def test_without_pending_complaints_there_is_nothing_to_discard(self, report):
        """CP-049-15. El descarte no es una cancelación libre."""
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        response = discard(agent, report)

        assert response.status_code == HTTP_CONFLICT
        report.refresh_from_db()
        assert report.status == Status.REPORTADO

    def test_it_is_not_offered_as_a_panel_button(self, report):
        """CP-049-16. Se ejecuta desde la bandeja, no desde el detalle."""
        content_complaint_for(report)
        detail = PanelReportDetailSerializer(report).data

        operations = {t["operation"] for t in detail["available_transitions"]}

        assert "descartar_por_moderacion" not in operations


class TestDismiss:
    def test_the_report_keeps_its_status_and_visibility(self, report, agent):
        """CP-049-17 (US-049 E4)."""
        complaint = content_complaint_for(report)

        response = dismiss(agent, report)

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        complaint.refresh_from_db()
        assert report.status == Status.REPORTADO
        assert Report.objects.publicly_visible().filter(pk=report.pk).exists()
        assert complaint.status == CStatus.DESESTIMADA
        assert not ReportStatusHistory.objects.filter(
            report=report,
            origin=Origin.MODERACION_MUNICIPAL,
        ).exists()

    def test_the_same_people_cannot_file_it_again(self, report, agent):
        """CP-049-18 (US-049 E4)."""
        complaint = content_complaint_for(report)
        dismiss(agent, report)

        response = client_for(complaint.reporter).post(
            f"/api/reports/{report.pk}/complaints/",
            {"reason": complaint.reason},
            format="json",
        )

        assert response.status_code == HTTP_CONFLICT


class TestReasonIsMandatoryAndPublic:
    @pytest.mark.parametrize("decide", [discard, dismiss], ids=["discard", "dismiss"])
    def test_without_a_reason_it_is_rejected(self, report, agent, decide):
        """CP-049-19 (US-049 E5)."""
        complaint = content_complaint_for(report)

        response = decide(agent, report, reason="   ")

        assert response.status_code == HTTP_BAD_REQUEST
        complaint.refresh_from_db()
        assert complaint.status == CStatus.PENDIENTE

    def test_any_citizen_reads_the_reason(self, report, agent):
        """CP-049-20 (US-049 E5). El detalle reducido, sin nada más."""
        content_complaint_for(report)
        discard(agent, report)

        response = client_for(UserFactory.create()).get(f"/api/reports/{report.pk}/")

        assert response.status_code == HTTP_OK
        assert response.data["is_moderation_notice"] is True
        assert response.data["moderation"]["reason"] == REASON
        assert response.data["moderation"]["can_appeal"] is False
        for private in ("photo", "description", "author", "comments"):
            assert private not in response.data

    def test_the_complainants_never_come_out(self, report, agent):
        """CP-049-21 (US-049 DoD)."""
        complaint = content_complaint_for(report)
        discard(agent, report)

        for viewer in (UserFactory.create(), report.author):
            body = str(client_for(viewer).get(f"/api/reports/{report.pk}/").data)
            assert str(complaint.reporter.email) not in body
            assert str(complaint.reporter.name) not in body

    def test_comments_and_likes_stay_closed(self, report, agent):
        """CP-049-22. Solo el aviso se abre: lo que cuelga del detalle, no."""
        content_complaint_for(report)
        discard(agent, report)
        stranger = client_for(UserFactory.create())

        assert stranger.get(f"/api/reports/{report.pk}/comments/").status_code == (
            HTTP_NOT_FOUND
        )
        assert stranger.post(f"/api/reports/{report.pk}/like/").status_code in {
            HTTP_NOT_FOUND,
            HTTP_FORBIDDEN,
        }

    def test_the_author_sees_the_full_detail_and_can_appeal(self, report, agent):
        """CP-049-23 (US-049 E5, E6)."""
        content_complaint_for(report)
        discard(agent, report)

        data = client_for(report.author).get(f"/api/reports/{report.pk}/").data

        assert "is_moderation_notice" not in data
        assert data["moderation"]["reason"] == REASON
        assert data["moderation"]["can_appeal"] is True


@pytest.fixture
def discarded(report, agent):
    content_complaint_for(report)
    discard(agent, report)
    report.refresh_from_db()
    return report


class TestAppeal:
    def test_the_author_appeals_and_the_report_stays_cancelled(self, discarded):
        """CP-049-24 (US-049 E6). Dirigida al administrador."""
        response = appeal(discarded.author, discarded)

        assert response.status_code == HTTP_CREATED
        discarded.refresh_from_db()
        assert discarded.status == Status.CANCELADO
        appeal_row = ResolutionAppeal.objects.get(report=discarded)
        assert appeal_row.kind == ResolutionAppeal.Kind.MODERACION
        assert appeal_row.status == ResolutionAppeal.Status.PENDIENTE
        assert response.data["moderation"]["appeal"]["status"] == "pendiente"
        assert response.data["moderation"]["can_appeal"] is False

    def test_it_shows_up_in_the_admin_review(self, discarded, admin):
        """CP-049-25 (US-049 E6)."""
        appeal(discarded.author, discarded)

        [entry] = rows(client_for(admin).get(APPEALS_URL))

        assert entry["report"]["id"] == discarded.pk
        assert entry["decision"]["reason"] == REASON
        assert len(entry["complaints"]) == 1

    def test_the_review_shows_the_photo_and_who_appealed(self, discarded, admin):
        """CP-049-49. Para juzgar sin abrir el reporte: foto y autor con perfil."""
        appeal(discarded.author, discarded)

        [entry] = rows(client_for(admin).get(APPEALS_URL))

        assert entry["report"]["photo"]
        assert entry["report"]["address"] == discarded.address
        assert entry["author"]["id"] == discarded.author_id
        assert entry["author"]["name"] == discarded.author.name

    def test_only_once(self, discarded):
        """CP-049-26 (US-049 E7)."""
        appeal(discarded.author, discarded)

        response = appeal(discarded.author, discarded)

        assert response.status_code == HTTP_CONFLICT

    def test_only_the_author(self, discarded):
        """CP-049-27."""
        response = appeal(UserFactory.create(), discarded)

        assert response.status_code in {HTTP_FORBIDDEN, HTTP_NOT_FOUND}
        assert not ResolutionAppeal.objects.exists()

    def test_it_is_not_part_of_the_closure_thread(self, discarded):
        """CP-049-28. Comparte modelo con US-048, pero no el hilo del cierre."""
        appeal(discarded.author, discarded)

        data = client_for(discarded.author).get(f"/api/reports/{discarded.pk}/").data

        assert data["resolution_appeals"] == []
        assert discarded.appeal_count == 0


class TestAdminResolution:
    def test_accepting_restores_the_previous_status(self, agent, admin):
        """CP-049-29 (US-049 E7). Al estado exacto, no a Reportado."""
        report = ReportFactory.create(
            municipality=agent.municipality,
            status=Status.EN_PROCESO,
        )
        report.operational_area = area_for(report)
        report.save()
        content_complaint_for(report)
        discard(agent, report)
        appeal(report.author, report)
        appeal_row = ResolutionAppeal.objects.get(report=report)

        response = client_for(admin).post(
            f"{APPEALS_URL}{appeal_row.pk}/accept/",
            {"reason": "El reclamo es legítimo."},
            format="json",
        )

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        assert report.status == Status.EN_PROCESO
        assert Report.objects.publicly_visible().filter(pk=report.pk).exists()
        entry = ReportStatusHistory.objects.filter(report=report).latest("created_at")
        assert entry.changed_by == admin
        assert entry.origin == Origin.REVERSION_MODERACION
        appeal_row.refresh_from_db()
        assert appeal_row.status == ResolutionAppeal.Status.ACEPTADA

    def test_rejecting_keeps_it_cancelled_without_a_second_appeal(
        self,
        discarded,
        admin,
    ):
        """CP-049-30 (US-049 E7)."""
        appeal(discarded.author, discarded)
        appeal_row = ResolutionAppeal.objects.get(report=discarded)

        response = client_for(admin).post(
            f"{APPEALS_URL}{appeal_row.pk}/reject/",
            {"reason": "La foto no corresponde al lugar."},
            format="json",
        )

        assert response.status_code == HTTP_OK
        discarded.refresh_from_db()
        assert discarded.status == Status.CANCELADO
        assert Notification.objects.filter(
            recipient=discarded.author,
            kind=Notification.Kind.APELACION_MODERACION_RECHAZADA,
        ).exists()
        assert appeal(discarded.author, discarded).status_code == HTTP_CONFLICT

    def test_an_appeal_is_resolved_once(self, discarded, admin):
        """CP-049-31."""
        appeal(discarded.author, discarded)
        appeal_row = ResolutionAppeal.objects.get(report=discarded)
        url = f"{APPEALS_URL}{appeal_row.pk}/reject/"
        client_for(admin).post(url, {"reason": "No."}, format="json")

        response = client_for(admin).post(url, {"reason": "No."}, format="json")

        assert response.status_code == HTTP_CONFLICT

    def test_ex_officio_reversal(self, discarded, admin):
        """CP-049-32 (US-049 E8). Sin apelación de por medio."""
        response = client_for(admin).post(
            f"/api/platform/reports/{discarded.pk}/revert-moderation/",
            {"reason": "Descarte injustificado."},
            format="json",
        )

        assert response.status_code == HTTP_OK
        discarded.refresh_from_db()
        assert discarded.status == Status.REPORTADO
        decision = ModerationDecision.objects.get(report=discarded)
        assert decision.reverted_by == admin
        assert discarded.active_discard() is None

    def test_reverting_twice_is_a_conflict(self, discarded, admin):
        """CP-049-33."""
        url = f"/api/platform/reports/{discarded.pk}/revert-moderation/"
        client_for(admin).post(url, {"reason": "Sí."}, format="json")

        response = client_for(admin).post(url, {"reason": "Sí."}, format="json")

        assert response.status_code == HTTP_CONFLICT

    def test_the_restore_guard_refuses_another_target(self, discarded, admin):
        """CP-049-34. La guarda impide volver a un estado distinto del previo."""
        from urbancheck.reports.services import GuardRejectedError  # noqa: PLC0415

        with pytest.raises(GuardRejectedError):
            apply_transition(
                discarded,
                "restituir_a_en_proceso",
                actor=Actor.PLATFORM_ADMIN,
                changed_by=admin,
                reason="Otro estado",
            )


class TestJurisdictionAndRoles:
    @pytest.mark.parametrize("decide", [discard, dismiss], ids=["discard", "dismiss"])
    def test_another_municipality_gets_a_404(self, decide):
        """CP-049-35 (US-049 E9). Igual que en US-034."""
        foreign = ReportFactory.create()
        content_complaint_for(foreign)
        agent = MunicipalAgentFactory.create()

        response = decide(agent, foreign)

        assert response.status_code == HTTP_NOT_FOUND
        foreign.refresh_from_db()
        assert foreign.status == Status.REPORTADO

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, OperatorFactory],
        ids=["ciudadano", "validador", "operario"],
    )
    def test_other_roles_cannot_moderate(self, report, factory):
        """CP-049-36 (US-049 E11)."""
        content_complaint_for(report)
        user = factory.create()

        assert client_for(user).get(INBOX_URL).status_code == HTTP_FORBIDDEN
        assert discard(user, report).status_code == HTTP_FORBIDDEN

    def test_the_admin_reads_the_inbox_of_the_chosen_municipality(self, report):
        """CP-049-50. Decisión del usuario (21/10): el admin ve, no resuelve."""
        content_complaint_for(report)
        content_complaint_for(ReportFactory.create())
        admin = PlatformAdminFactory.create()
        url = f"{INBOX_URL}?municipality={report.municipality_id}"

        [entry] = rows(client_for(admin).get(url))
        count = client_for(admin).get(
            f"{INBOX_URL}count/?municipality={report.municipality_id}",
        )

        assert entry["id"] == report.pk
        assert count.data == {"pending": 1}
        assert discard(admin, report).status_code == HTTP_FORBIDDEN
        assert dismiss(admin, report).status_code == HTTP_FORBIDDEN

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, OperatorFactory],
        ids=["ciudadano", "validador", "operario"],
    )
    def test_other_roles_cannot_review_appeals(self, discarded, factory):
        """CP-049-37 (US-049 E11). Las apelaciones son del panel."""
        assert client_for(factory.create()).get(APPEALS_URL).status_code == (
            HTTP_FORBIDDEN
        )

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, OperatorFactory, MunicipalAgentFactory],
        ids=["ciudadano", "validador", "operario", "agente"],
    )
    def test_only_the_admin_reverts_ex_officio(self, discarded, factory):
        """CP-049-43 (US-049 E8). La reversión sin apelación no es del municipio."""
        response = client_for(factory.create()).post(
            f"/api/platform/reports/{discarded.pk}/revert-moderation/",
            {"reason": "x"},
            format="json",
        )

        assert response.status_code == HTTP_FORBIDDEN


class TestAgentReviewsAppealsOfTheirCity:
    """Decisión del usuario (20/10): el agente también resuelve apelaciones,
    pero solo las de reportes de su municipalidad."""

    def test_the_agent_sees_only_the_appeals_of_their_city(self, discarded, agent):
        """CP-049-44."""
        appeal(discarded.author, discarded)
        foreign = ReportFactory.create()
        foreign_agent = MunicipalAgentFactory.create(municipality=foreign.municipality)
        content_complaint_for(foreign)
        discard(foreign_agent, foreign)
        appeal(foreign.author, foreign)

        mine = rows(client_for(agent).get(APPEALS_URL))
        theirs = rows(client_for(foreign_agent).get(APPEALS_URL))

        assert [entry["report"]["id"] for entry in mine] == [discarded.pk]
        assert [entry["report"]["id"] for entry in theirs] == [foreign.pk]

    def test_the_agent_accepts_and_the_report_is_restored(self, discarded, agent):
        """CP-049-45. La reversión queda en el historial con el agente."""
        appeal(discarded.author, discarded)
        appeal_row = ResolutionAppeal.objects.get(report=discarded)

        response = client_for(agent).post(
            f"{APPEALS_URL}{appeal_row.pk}/accept/",
            {"reason": "Revisamos de nuevo: es legítimo."},
            format="json",
        )

        assert response.status_code == HTTP_OK
        discarded.refresh_from_db()
        assert discarded.status == Status.REPORTADO
        entry = ReportStatusHistory.objects.filter(report=discarded).latest(
            "created_at",
        )
        assert entry.changed_by == agent
        assert entry.origin == Origin.REVERSION_MODERACION

    def test_the_agent_rejects_and_there_is_no_second_appeal(self, discarded, agent):
        """CP-049-46."""
        appeal(discarded.author, discarded)
        appeal_row = ResolutionAppeal.objects.get(report=discarded)

        client_for(agent).post(
            f"{APPEALS_URL}{appeal_row.pk}/reject/",
            {"reason": "Se mantiene."},
            format="json",
        )

        discarded.refresh_from_db()
        assert discarded.status == Status.CANCELADO
        assert appeal(discarded.author, discarded).status_code == HTTP_CONFLICT

    def test_another_city_gets_a_404(self, discarded):
        """CP-049-47 (US-049 E9). Igual que en US-034."""
        appeal(discarded.author, discarded)
        appeal_row = ResolutionAppeal.objects.get(report=discarded)
        stranger = MunicipalAgentFactory.create()

        response = client_for(stranger).post(
            f"{APPEALS_URL}{appeal_row.pk}/accept/",
            {"reason": "x"},
            format="json",
        )

        assert response.status_code == HTTP_NOT_FOUND
        discarded.refresh_from_db()
        assert discarded.status == Status.CANCELADO

    def test_the_admin_can_narrow_to_one_municipality(self, discarded, admin):
        """CP-049-48."""
        appeal(discarded.author, discarded)
        other = ReportFactory.create().municipality

        assert (
            rows(client_for(admin).get(f"{APPEALS_URL}?municipality={other.pk}")) == []
        )
        assert (
            len(
                rows(
                    client_for(admin).get(
                        f"{APPEALS_URL}?municipality={discarded.municipality_id}",
                    ),
                ),
            )
            == 1
        )


class TestListingFlag:
    def test_the_panel_list_flags_pending_complaints(self, report, agent):
        """CP-049-38 (US-049 E12)."""
        content_complaint_for(report)
        ReportComplaintFactory.create(report=report)  # dato personal: no cuenta

        response = client_for(agent).get("/api/panel/reports/?status=reportado")

        [row] = rows(response)
        assert row["pending_complaint_count"] == 1

    def test_the_panel_detail_lists_complaints_and_their_state(self, report, agent):
        """CP-049-39. El detalle muestra las denuncias y su resolución."""
        content_complaint_for(report)
        dismiss(agent, report)

        data = client_for(agent).get(f"/api/panel/reports/{report.pk}/").data

        [complaint] = data["complaints"]
        assert complaint["status"] == CStatus.DESESTIMADA
        assert data["pending_complaint_count"] == 0


class TestValidatorRejectionOrigin:
    """La lección de US-038 otra vez: el origen dice quién decidió."""

    def test_a_rejection_is_a_field_decision(self):
        """CP-049-40. Hasta US-049 quedaba como ``manual``."""
        report = ReportFactory.create(status=Status.PENDIENTE_VALIDACION)
        validator = ValidatorFactory.create(municipality=report.municipality)

        apply_transition(
            report,
            "rechazar",
            actor=Actor.VALIDATOR,
            changed_by=validator,
            reason="No existe",
        )

        entry = ReportStatusHistory.objects.get(report=report, status=Status.CANCELADO)
        assert entry.origin == Origin.VALIDACION_TERRENO
        detail = PanelReportDetailSerializer(
            Report.objects.prefetch_related("status_history").get(pk=report.pk),
        ).data
        assert detail["validation"]["outcome"] == "rechazado"

    def test_the_migration_fixes_the_rejections_left_as_manual(self):
        """CP-049-41. Y no toca la cancelación del agente desde En proceso."""
        report = ReportFactory.create(status=Status.CANCELADO, with_history=False)
        validator = ValidatorFactory.create(municipality=report.municipality)
        rejection = ReportStatusHistory.objects.create(
            report=report,
            previous_status=Status.PENDIENTE_VALIDACION,
            status=Status.CANCELADO,
            changed_by=validator,
            origin=Origin.MANUAL,
        )
        cancellation = ReportStatusHistory.objects.create(
            report=report,
            previous_status=Status.EN_PROCESO,
            status=Status.CANCELADO,
            changed_by=validator,
            origin=Origin.MANUAL,
        )
        module = importlib.import_module(
            "urbancheck.reports.migrations.0015_moderation",
        )

        module.backfill_rejection_origin(django_apps, None)

        rejection.refresh_from_db()
        cancellation.refresh_from_db()
        assert rejection.origin == Origin.VALIDACION_TERRENO
        assert cancellation.origin == Origin.MANUAL


def test_closure_appeals_still_reach_the_thread():
    """CP-049-42. Las objeciones de cierre de US-048 siguen en su hilo."""
    appeal_row = ResolutionAppealFactory.create()

    data = PanelReportDetailSerializer(appeal_row.report).data

    assert [a["id"] for a in data["resolution_appeals"]] == [appeal_row.pk]
