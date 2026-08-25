"""US-013 — la máquina de estados es la única fuente de verdad.

El test recorre **todas** las combinaciones de estado origen y destino y
verifica que solo las siete transiciones declaradas son aceptadas.
"""

import itertools

import pytest

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.services import ReasonRequiredError
from urbancheck.reports.services import TransitionError
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import TRANSITIONS
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.state_machine import is_valid
from urbancheck.reports.state_machine import transitions_from
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

ALL_STATUSES = [status.value for status in Report.Status]
DECLARED = {(t.source, t.target) for t in TRANSITIONS}


@pytest.mark.parametrize(
    ("source", "target"),
    list(itertools.product(ALL_STATUSES, ALL_STATUSES)),
)
def test_only_declared_pairs_are_valid(source, target):
    assert is_valid(source, target) is ((source, target) in DECLARED)


def test_final_statuses_have_no_way_out():
    for status in (Report.Status.RESUELTO, Report.Status.CANCELADO):
        assert transitions_from(status) == ()


class TestApplyTransition:
    @pytest.mark.parametrize("transition", TRANSITIONS, ids=lambda t: t.operation)
    def test_every_declared_transition_runs(self, transition):
        report = ReportFactory.create(status=transition.source)
        actor_factory = (
            ValidatorFactory
            if transition.actor == Actor.VALIDATOR
            else MunicipalAgentFactory
        )
        user = actor_factory.create(municipality=report.municipality)

        apply_transition(
            report,
            transition.operation,
            actor=transition.actor,
            changed_by=user,
            reason="motivo" if transition.requires_reason else "",
        )

        report.refresh_from_db()
        assert report.status == transition.target

    @pytest.mark.parametrize("transition", TRANSITIONS, ids=lambda t: t.operation)
    def test_transition_from_the_wrong_state_is_rejected(self, transition):
        wrong_source = next(s for s in ALL_STATUSES if s != transition.source)
        report = ReportFactory.create(status=wrong_source)
        user = MunicipalAgentFactory.create(municipality=report.municipality)

        with pytest.raises(TransitionError):
            apply_transition(
                report,
                transition.operation,
                actor=transition.actor,
                changed_by=user,
                reason="motivo",
            )

        report.refresh_from_db()
        assert report.status == wrong_source

    def test_the_wrong_actor_cannot_run_a_transition(self):
        """Validar es del validador; el agente no puede hacerlo desde el panel."""
        report = ReportFactory.create(status=Report.Status.PENDIENTE_VALIDACION)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        with pytest.raises(TransitionError):
            apply_transition(report, "validar", actor=Actor.MUNICIPAL_AGENT, changed_by=agent)

    def test_an_unknown_operation_is_rejected(self):
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        with pytest.raises(TransitionError):
            apply_transition(report, "teletransportar", actor=Actor.MUNICIPAL_AGENT, changed_by=agent)


class TestReasonIsEnforced:
    @pytest.mark.parametrize(
        "transition",
        [t for t in TRANSITIONS if t.requires_reason],
        ids=lambda t: t.operation,
    )
    def test_reason_is_mandatory_where_declared(self, transition):
        report = ReportFactory.create(status=transition.source)
        user = (
            ValidatorFactory if transition.actor == Actor.VALIDATOR else MunicipalAgentFactory
        ).create(municipality=report.municipality)

        with pytest.raises(ReasonRequiredError):
            apply_transition(
                report,
                transition.operation,
                actor=transition.actor,
                changed_by=user,
                reason="   ",
            )

        report.refresh_from_db()
        assert report.status == transition.source


class TestHistory:
    def test_every_change_writes_the_history_entry(self):
        report = ReportFactory.create(status=Report.Status.REPORTADO, with_history=False)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        apply_transition(report, "procesar", actor=Actor.MUNICIPAL_AGENT, changed_by=agent)

        entry = ReportStatusHistory.objects.get(report=report)
        assert entry.previous_status == Report.Status.REPORTADO
        assert entry.status == Report.Status.EN_PROCESO
        assert entry.changed_by == agent

    def test_the_reason_is_stored(self):
        report = ReportFactory.create(status=Report.Status.EN_PROCESO, with_history=False)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)

        apply_transition(
            report,
            "cancelar",
            actor=Actor.MUNICIPAL_AGENT,
            changed_by=agent,
            reason="El reclamo estaba duplicado",
        )

        entry = ReportStatusHistory.objects.get(report=report)
        assert entry.reason == "El reclamo estaba duplicado"


class TestConcurrency:
    def test_a_second_simultaneous_transition_is_rejected(self):
        """Dos pestañas del panel: la segunda encuentra el estado ya cambiado."""
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)
        stale = Report.objects.get(pk=report.pk)

        apply_transition(report, "procesar", actor=Actor.MUNICIPAL_AGENT, changed_by=agent)

        # ``stale`` todavía cree que el reporte está en Reportado.
        with pytest.raises(TransitionError):
            apply_transition(stale, "procesar", actor=Actor.MUNICIPAL_AGENT, changed_by=agent)

        assert ReportStatusHistory.objects.filter(report=report).count() == 2


class TestEvent:
    def test_the_single_status_change_event_is_emitted(self):
        from urbancheck.reports.signals import report_status_changed

        received = []

        def listener(**kwargs):
            received.append(kwargs)

        report_status_changed.connect(listener)
        try:
            report = ReportFactory.create(status=Report.Status.REPORTADO)
            agent = MunicipalAgentFactory.create(municipality=report.municipality)
            apply_transition(report, "procesar", actor=Actor.MUNICIPAL_AGENT, changed_by=agent)
        finally:
            report_status_changed.disconnect(listener)

        assert len(received) == 1
        assert received[0]["previous_status"] == Report.Status.REPORTADO
        assert received[0]["new_status"] == Report.Status.EN_PROCESO
        assert received[0]["changed_by"] == agent
