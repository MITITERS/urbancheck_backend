"""Consultas y guardas del manager de usuarios (US-034, US-035, US-013).

El manager es el punto donde se resuelven dos cosas que el panel usa en cada
pantalla: qué usuarios ve cada quien —acotado por jurisdicción— y cuánta
actividad tuvo cada cuenta de trabajo. Las dos anotaciones existen para no
producir un N+1 en la tabla, así que se prueban contra la base.
"""

from __future__ import annotations

import pytest

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db


class TestForUser:
    """``User.objects.for_user`` acota por municipalidad, igual que los reportes."""

    def test_it_returns_the_users_of_the_same_municipality(self):
        municipality = MunicipalityFactory.create()
        mine = ValidatorFactory.create(municipality=municipality)

        result = User.objects.for_user(mine)

        assert mine in result

    def test_it_leaves_out_the_users_of_another_municipality(self):
        mine = MunicipalAgentFactory.create()
        theirs = ValidatorFactory.create(municipality=MunicipalityFactory.create())

        assert theirs not in User.objects.for_user(mine)

    def test_a_user_without_municipality_sees_nobody(self):
        """Default seguro: sin jurisdicción, ningún usuario.

        Es el mismo criterio que ``Report.objects.for_user``. Devolver todo
        cuando falta el dato es como se filtran los datos entre municipios.
        """
        admin = PlatformAdminFactory.create()

        assert not User.objects.for_user(admin).exists()

    def test_an_object_without_the_attribute_also_sees_nobody(self):
        assert not User.objects.for_user(object()).exists()


class TestValidationCount:
    """Validaciones en terreno por usuario, contadas desde el historial."""

    @staticmethod
    def _history(report, user, previous, status):
        return ReportStatusHistory.objects.create(
            report=report,
            previous_status=previous,
            status=status,
            changed_by=user,
        )

    def test_a_validator_without_activity_counts_zero(self):
        validator = ValidatorFactory.create()

        annotated = User.objects.with_validation_count().get(pk=validator.pk)

        assert annotated.validation_count == 0

    def test_every_exit_from_pending_validation_counts(self):
        validator = ValidatorFactory.create()
        report = ReportFactory.create()
        self._history(
            report,
            validator,
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
        )
        self._history(
            report,
            validator,
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.CANCELADO,
        )

        annotated = User.objects.with_validation_count().get(pk=validator.pk)

        # Validar y rechazar son las dos caras del mismo trabajo de terreno.
        assert annotated.validation_count == 2

    def test_a_panel_transition_is_not_a_validation(self):
        agent = MunicipalAgentFactory.create()
        report = ReportFactory.create()
        self._history(
            report,
            agent,
            Report.Status.REPORTADO,
            Report.Status.EN_PROCESO,
        )

        annotated = User.objects.with_validation_count().get(pk=agent.pk)

        assert annotated.validation_count == 0

    def test_it_does_not_count_what_another_user_did(self):
        validator = ValidatorFactory.create()
        other = ValidatorFactory.create()
        report = ReportFactory.create()
        self._history(
            report,
            other,
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
        )

        annotated = User.objects.with_validation_count().get(pk=validator.pk)

        assert annotated.validation_count == 0


class TestManagementCount:
    """Gestiones del agente: es el complemento exacto de las validaciones."""

    @staticmethod
    def _history(report, user, previous, status):
        return ReportStatusHistory.objects.create(
            report=report,
            previous_status=previous,
            status=status,
            changed_by=user,
        )

    def test_it_counts_the_panel_transitions(self):
        agent = MunicipalAgentFactory.create()
        report = ReportFactory.create()
        self._history(report, agent, Report.Status.REPORTADO, Report.Status.EN_PROCESO)
        self._history(report, agent, Report.Status.EN_PROCESO, Report.Status.RESUELTO)

        annotated = User.objects.with_management_count().get(pk=agent.pk)

        assert annotated.management_count == 2

    def test_a_field_validation_is_not_a_management(self):
        """Las validaciones tienen su propia columna y su propio rol.

        Si contaran acá, un validador aparecería con gestiones que nunca hizo
        desde el panel.
        """
        validator = ValidatorFactory.create()
        report = ReportFactory.create()
        self._history(
            report,
            validator,
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
        )

        annotated = User.objects.with_management_count().get(pk=validator.pk)

        assert annotated.management_count == 0

    def test_the_two_annotations_can_be_combined(self):
        """La tabla del panel pide las dos cifras en una sola consulta."""
        agent = MunicipalAgentFactory.create()
        report = ReportFactory.create()
        self._history(report, agent, Report.Status.REPORTADO, Report.Status.EN_PROCESO)

        annotated = (
            User.objects.with_validation_count()
            .with_management_count()
            .get(pk=agent.pk)
        )

        assert annotated.validation_count == 0
        assert annotated.management_count == 1


class TestCreateUserGuards:
    """Las guardas del manager, que son las que sostienen el modelo sin username."""

    def test_creating_a_user_without_email_is_refused(self):
        # El email es el identificador: sin él la cuenta no se puede autenticar.
        with pytest.raises(ValueError, match="email must be set"):
            User.objects.create_user(email="", password="x")  # noqa: S106

    def test_a_superuser_must_be_staff(self):
        with pytest.raises(ValueError, match="is_staff=True"):
            User.objects.create_superuser(
                email="admin@example.com",
                password="x",  # noqa: S106
                is_staff=False,
            )

    def test_a_superuser_must_be_superuser(self):
        with pytest.raises(ValueError, match="is_superuser=True"):
            User.objects.create_superuser(
                email="admin@example.com",
                password="x",  # noqa: S106
                is_superuser=False,
            )

    def test_the_email_is_normalized(self):
        user = User.objects.create_user(
            email="Agente@VillaMaria.GOB.AR",
            password="x",  # noqa: S106
        )

        # Django normaliza el dominio, no la parte local.
        assert user.email == "Agente@villamaria.gob.ar"

    def test_a_user_can_be_created_without_a_password(self):
        """Es lo que hace ``createsuperuser`` en modo no interactivo."""
        created = User.objects.create_user(email="sin-clave@example.com")

        assert not created.has_usable_password()
