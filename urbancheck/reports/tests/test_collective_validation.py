"""US-040 — validación colectiva de un reporte por umbral de confirmaciones."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.notifications.models import Notification
from urbancheck.reports.collective_validation import evaluate
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.state_machine import Origin
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201

THRESHOLD = 3


@pytest.fixture(autouse=True)
def _low_threshold(settings):
    """Umbral bajo para que los tests no tengan que crear diez usuarios.

    Que el valor se pueda cambiar así es, además, el escenario 7: el módulo lo
    lee de configuración en cada evaluación.
    """
    settings.COLLECTIVE_VALIDATION_THRESHOLD = THRESHOLD


@pytest.fixture
def pending():
    return ReportFactory.create(status=Report.Status.PENDIENTE_VALIDACION)


def confirm(report, times=1):
    """``times`` vecinos distintos confirman el reporte."""
    for _ in range(times):
        LikeFactory.create(report=report, user=UserFactory.create())
    return evaluate(report)


class TestThreshold:
    def test_reaching_the_threshold_validates_the_report(self, pending):
        """Escenario 1."""
        confirm(pending, THRESHOLD)

        pending.refresh_from_db()
        assert pending.status == Report.Status.REPORTADO

    def test_one_confirmation_below_the_threshold_does_nothing(self, pending):
        confirm(pending, THRESHOLD - 1)

        pending.refresh_from_db()
        assert pending.status == Report.Status.PENDIENTE_VALIDACION

    def test_the_transition_has_no_individual_responsible(self, pending):
        """Escenario 1: no la decidió una persona, la decidió la cantidad."""
        confirm(pending, THRESHOLD)

        entry = ReportStatusHistory.objects.get(
            report=pending,
            status=Report.Status.REPORTADO,
        )
        assert entry.changed_by is None
        assert entry.origin == Origin.VALIDACION_COLECTIVA

    def test_the_history_records_how_many_confirmations_it_had(self, pending):
        """Escenario 9: el panel lo lee de ahí, sin recalcular sobre un conteo
        que para entonces ya cambió."""
        confirm(pending, THRESHOLD)

        entry = ReportStatusHistory.objects.get(
            report=pending,
            status=Report.Status.REPORTADO,
        )
        assert entry.confirmation_count == THRESHOLD

    def test_the_author_is_notified(self, pending):
        """Escenario 1: cuelga del mismo evento que el resto de las transiciones."""
        confirm(pending, THRESHOLD)

        notification = Notification.objects.get(
            report=pending,
            kind=Notification.Kind.CAMBIO_ESTADO,
        )
        assert notification.recipient == pending.author
        assert notification.new_status == Report.Status.REPORTADO

    def test_the_threshold_is_read_from_configuration(self, pending, settings):
        """Escenario 7: se aplica el valor vigente al evaluar, sin redeploy."""
        settings.COLLECTIVE_VALIDATION_THRESHOLD = THRESHOLD + 5
        confirm(pending, THRESHOLD)
        pending.refresh_from_db()
        assert pending.status == Report.Status.PENDIENTE_VALIDACION

        settings.COLLECTIVE_VALIDATION_THRESHOLD = THRESHOLD
        evaluate(pending)

        pending.refresh_from_db()
        assert pending.status == Report.Status.REPORTADO


class TestWhoCounts:
    def test_the_author_does_not_count_but_still_shows_in_the_counter(self, pending):
        """Escenario 2."""
        LikeFactory.create(report=pending, user=pending.author)
        confirm(pending, THRESHOLD - 1)

        pending.refresh_from_db()
        assert pending.status == Report.Status.PENDIENTE_VALIDACION
        # El contador público sí lo cuenta: son dos cifras distintas.
        assert pending.likes.count() == THRESHOLD
        assert pending.confirmation_count() == THRESHOLD - 1

    @pytest.mark.parametrize(
        "factory",
        [
            ValidatorFactory,
            MunicipalAgentFactory,
            PlatformAdminFactory,
            OperatorFactory,
        ],
        ids=["validador", "agente", "admin", "operario"],
    )
    def test_work_accounts_do_not_count(self, pending, factory):
        """Escenario 3: la confirmación municipal va por la vía de US-036."""
        LikeFactory.create(report=pending, user=factory.create())
        confirm(pending, THRESHOLD - 1)

        pending.refresh_from_db()
        assert pending.status == Report.Status.PENDIENTE_VALIDACION


class TestIrreversibility:
    def test_removing_likes_below_the_threshold_keeps_it_pending(self, pending):
        """Escenario 4: el umbral vuelve a evaluarse cuando el conteo sube."""
        confirm(pending, THRESHOLD - 1)
        Like.objects.filter(report=pending).first().delete()

        pending.refresh_from_db()
        assert pending.status == Report.Status.PENDIENTE_VALIDACION

        confirm(pending, 2)
        pending.refresh_from_db()
        assert pending.status == Report.Status.REPORTADO

    def test_removing_likes_after_the_threshold_does_not_revert(self, pending):
        """Escenario 5: la transición es irreversible por esta vía."""
        confirm(pending, THRESHOLD)
        Like.objects.filter(report=pending).delete()
        evaluate(pending)

        pending.refresh_from_db()
        assert pending.status == Report.Status.REPORTADO

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.REPORTADO,
            Report.Status.EN_PROCESO,
            Report.Status.RESUELTO,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
        ],
    )
    def test_other_states_do_not_transition(self, status):
        """Escenario 6: un reporte rechazado no se resucita con me gusta."""
        report = ReportFactory.create(status=status)
        confirm(report, THRESHOLD + 2)

        report.refresh_from_db()
        assert report.status == status

    def test_a_second_evaluation_does_not_duplicate_the_transition(self, pending):
        """Escenario 8, por el lado del efecto.

        Una sola transición y un solo asiento en el historial.
        """
        confirm(pending, THRESHOLD)
        evaluate(pending)
        evaluate(pending)

        assert (
            ReportStatusHistory.objects.filter(
                report=pending,
                status=Report.Status.REPORTADO,
            ).count()
            == 1
        )


class TestThroughTheApi:
    def test_the_like_that_reaches_the_threshold_validates_in_the_same_call(
        self,
        pending,
    ):
        """La evaluación es sincrónica al persistir el me gusta, no un job."""
        for _ in range(THRESHOLD - 1):
            LikeFactory.create(report=pending, user=UserFactory.create())

        client = APIClient()
        client.force_authenticate(UserFactory.create())
        response = client.post(f"/api/reports/{pending.pk}/like/")

        assert response.status_code == HTTP_CREATED
        # El cliente se entera en la misma respuesta y puede refrescar.
        assert response.data["status"] == Report.Status.REPORTADO
        pending.refresh_from_db()
        assert pending.status == Report.Status.REPORTADO

    def test_it_leaves_the_validation_inbox(self, pending):
        """Escenario 10: desaparece de los pendientes de US-037."""
        validator = ValidatorFactory.create(municipality=pending.municipality)
        client = APIClient()
        client.force_authenticate(validator)
        assert client.get("/api/validation/reports/").data["count"] == 1

        confirm(pending, THRESHOLD)

        assert client.get("/api/validation/reports/").data["count"] == 0

    def test_it_becomes_available_in_the_panel(self, pending):
        """Escenario 10: queda disponible en el panel de su municipalidad."""
        confirm(pending, THRESHOLD)
        OperationalAreaFactory.create(municipality=pending.municipality)
        agent = MunicipalAgentFactory.create(municipality=pending.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        detail = client.get(f"/api/panel/reports/{pending.pk}/").data

        assert detail["status"] == Report.Status.REPORTADO
        operations = {t["operation"] for t in detail["available_transitions"]}
        assert "procesar" in operations

    def test_the_panel_history_shows_it_was_collective(self, pending):
        """Escenario 9, sin exponer quiénes confirmaron."""
        confirm(pending, THRESHOLD)
        agent = MunicipalAgentFactory.create(municipality=pending.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        history = client.get(f"/api/panel/reports/{pending.pk}/").data["status_history"]

        entry = next(h for h in history if h["status"] == Report.Status.REPORTADO)
        assert entry["origin"] == Origin.VALIDACION_COLECTIVA
        assert entry["confirmation_count"] == THRESHOLD
        assert entry["changed_by"] is None

    def test_it_is_not_reported_as_a_field_validation(self, pending):
        """La validación colectiva no inventa un validador que no existió."""
        confirm(pending, THRESHOLD)
        agent = MunicipalAgentFactory.create(municipality=pending.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        detail = client.get(f"/api/panel/reports/{pending.pk}/").data
        assert detail["validation"] is None

    def test_the_panel_says_the_community_validated_it(self, pending):
        """No alcanza con no mentir: el panel tiene que decir qué sí pasó.

        Dejar `validation` en nulo y nada más hacía que el encabezado del
        detalle no mostrara **nada**, y un reporte validado por la comunidad se
        leía como uno que nadie validó.
        """
        confirm(pending, THRESHOLD)
        agent = MunicipalAgentFactory.create(municipality=pending.municipality)
        client = APIClient()
        client.force_authenticate(agent)

        collective = client.get(f"/api/panel/reports/{pending.pk}/").data[
            "collective_validation"
        ]

        assert collective is not None
        assert collective["confirmation_count"] == THRESHOLD
        assert collective["validated_at"] is not None

    def test_the_platform_admin_sees_it_too(self, pending):
        confirm(pending, THRESHOLD)
        client = APIClient()
        client.force_authenticate(PlatformAdminFactory.create())

        detail = client.get(f"/api/panel/reports/{pending.pk}/").data

        assert detail["collective_validation"]["confirmation_count"] == THRESHOLD
        assert detail["validation"] is None

    def test_a_field_validated_report_carries_no_collective_validation(self):
        """El complemento: los dos campos no pueden estar los dos llenos."""
        report = ReportFactory.create(status=Report.Status.PENDIENTE_VALIDACION)
        validator = ValidatorFactory.create(municipality=report.municipality)
        apply_transition(
            report,
            "validar",
            actor=Actor.VALIDATOR,
            changed_by=validator,
        )
        client = APIClient()
        client.force_authenticate(
            MunicipalAgentFactory.create(municipality=report.municipality),
        )

        detail = client.get(f"/api/panel/reports/{report.pk}/").data

        assert detail["collective_validation"] is None
        assert detail["validation"] is not None


class TestAuthorNotice:
    """El aviso al autor no puede atribuirle la validación a un validador.

    Es la misma trampa que US-040 destapó en el panel, un nivel más abajo: el
    texto se elegía por el par (estado anterior, estado nuevo), y ese par pasó a
    significar dos cosas. El discriminador es el origen.
    """

    def test_it_does_not_say_a_validator_confirmed_it_on_site(self, pending):
        confirm(pending, THRESHOLD)

        notification = Notification.objects.get(
            report=pending,
            kind=Notification.Kind.CAMBIO_ESTADO,
        )

        assert "validador" not in notification.message.lower()
        assert "en el lugar" not in notification.message.lower()

    def test_it_says_the_neighbours_confirmed_it(self, pending):
        confirm(pending, THRESHOLD)

        notification = Notification.objects.get(
            report=pending,
            kind=Notification.Kind.CAMBIO_ESTADO,
        )

        assert "vecinos" in notification.message.lower()

    def test_a_field_validation_still_names_the_validator(self):
        """El caso general no se tocó: sin origen ambiguo, el par sigue mandando."""
        report = ReportFactory.create(status=Report.Status.PENDIENTE_VALIDACION)
        validator = ValidatorFactory.create(municipality=report.municipality)

        apply_transition(
            report,
            "validar",
            actor=Actor.VALIDATOR,
            changed_by=validator,
        )

        notification = Notification.objects.get(
            report=report,
            kind=Notification.Kind.CAMBIO_ESTADO,
        )
        assert "validador" in notification.message.lower()
