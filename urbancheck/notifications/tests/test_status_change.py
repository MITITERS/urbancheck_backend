"""US-011 — notificaciones de cambio de estado."""

import pytest

from urbancheck.notifications.models import Notification
from urbancheck.reports.models import Report
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import TRANSITIONS
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.factories import area_for
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db


def actor_for(transition):
    factory = (
        ValidatorFactory if transition.actor == Actor.VALIDATOR else MunicipalAgentFactory
    )
    return factory


def run(transition, report, user):
    """Ejecuta la transición completando lo que cada una exige.

    El motivo y el área son requisitos declarados en la tabla de transiciones,
    así que se leen de ahí en vez de repetirlos test por test.
    """
    return apply_transition(
        report,
        transition.operation,
        actor=transition.actor,
        changed_by=user,
        reason="motivo" if transition.requires_reason else "",
        operational_area=area_for(report) if transition.requires_area else None,
    )


class TestOneNotificationPerTransition:
    @pytest.mark.parametrize("transition", TRANSITIONS, ids=lambda t: t.operation)
    def test_each_transition_notifies_the_author_exactly_once(self, transition):
        report = ReportFactory.create(status=transition.source)
        user = actor_for(transition).create(municipality=report.municipality)

        run(transition, report, user)

        notifications = Notification.objects.filter(
            report=report,
            kind=Notification.Kind.CAMBIO_ESTADO,
        )
        assert notifications.count() == 1
        assert notifications.first().recipient == report.author

    @pytest.mark.parametrize("transition", TRANSITIONS, ids=lambda t: t.operation)
    def test_nobody_else_is_notified(self, transition):
        """Escenario 8: el destinatario es siempre y solo el autor."""
        report = ReportFactory.create(status=transition.source)
        bystander = UserFactory.create()
        CommentFactory.create(report=report, author=bystander)
        user = actor_for(transition).create(municipality=report.municipality)

        run(transition, report, user)

        assert not Notification.objects.filter(
            recipient=bystander,
            kind=Notification.Kind.CAMBIO_ESTADO,
        ).exists()

    def test_the_notification_carries_the_change(self):
        """Escenario 7: estado anterior, nuevo, fecha y acceso al reporte."""
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        apply_transition(
            report,
            "procesar",
            actor=Actor.MUNICIPAL_AGENT,
            changed_by=agent,
            operational_area=area_for(report),
        )

        notification = Notification.objects.get(report=report)
        assert notification.previous_status == Report.Status.REPORTADO
        assert notification.new_status == Report.Status.EN_PROCESO
        assert notification.created_at is not None
        assert notification.report_id == report.id

    def test_a_cancellation_explains_the_reason(self):
        report = ReportFactory.create(status=Report.Status.EN_PROCESO)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        apply_transition(
            report,
            "cancelar",
            actor=Actor.MUNICIPAL_AGENT,
            changed_by=agent,
            reason="La obra ya fue ejecutada",
        )

        notification = Notification.objects.get(report=report)
        assert notification.reason == "La obra ya fue ejecutada"
        assert "La obra ya fue ejecutada" in notification.message

    def test_messages_avoid_internal_status_names(self):
        report = ReportFactory.create(status=Report.Status.PENDIENTE_VALIDACION)
        validator = ValidatorFactory.create(municipality=report.municipality)

        apply_transition(report, "validar", actor=Actor.VALIDATOR, changed_by=validator)

        message = Notification.objects.get(report=report).message
        assert "pendiente_validacion" not in message
        assert "reportado" not in message


class TestPushFailureIsolation:
    def test_a_push_failure_does_not_revert_the_transition(self, monkeypatch):
        def explode(_notification):
            msg = "El proveedor de push está caído"
            raise RuntimeError(msg)

        monkeypatch.setattr("urbancheck.notifications.push.send_push", explode)
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        apply_transition(
            report,
            "procesar",
            actor=Actor.MUNICIPAL_AGENT,
            changed_by=agent,
            operational_area=area_for(report),
        )

        report.refresh_from_db()
        assert report.status == Report.Status.EN_PROCESO
        # La notificación igual queda en la bandeja.
        assert Notification.objects.filter(report=report).exists()


class TestSocialNotificationsStillWork:
    def test_a_new_comment_still_notifies_the_author(self):
        """Regresión de US-033: los avisos sociales no cambiaron."""
        report = ReportFactory.create()
        comment = CommentFactory.create(report=report)

        from urbancheck.notifications.services import notify_new_comment

        notification = notify_new_comment(comment)

        assert notification.kind == Notification.Kind.NUEVO_COMENTARIO
        assert notification.recipient == report.author
        # Los avisos sociales no tienen transición asociada.
        assert notification.previous_status == ""
        assert notification.new_status == ""
