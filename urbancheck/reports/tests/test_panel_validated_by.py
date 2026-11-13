"""Quién validó el reporte, en el detalle del panel.

El nombre del validador ya viajaba dentro del historial, pero ahí está mezclado
con las acciones del municipio y sin decir quién es cada uno. Estos campos
responden «¿quién salió a mirar esto?» sin leer la lista entera.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.state_machine import Origin
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def agent_client(municipality) -> APIClient:
    client = APIClient()
    client.force_authenticate(MunicipalAgentFactory.create(municipality=municipality))
    return client


def detail(client: APIClient, report: Report):
    return client.get(f"/api/panel/reports/{report.id}/")


def decide(report: Report, validator, status=Report.Status.REPORTADO, **overrides):
    """Deja el asiento que produce decidir en terreno: validar o rechazar.

    El origen va explícito porque es lo que escribe ``apply_transition`` desde
    la tabla, y es por lo que el detalle distingue una decisión de terreno de
    una validación colectiva (US-040): las dos salen del mismo estado y llegan
    al mismo, así que sin el origen serían indistinguibles.
    """
    return ReportStatusHistory.objects.create(
        report=report,
        previous_status=Report.Status.PENDIENTE_VALIDACION,
        status=status,
        changed_by=validator,
        origin=Origin.VALIDACION_TERRENO,
        **overrides,
    )


class TestValidatedBy:
    def test_names_the_validator_that_confirmed_it(self, agent_client, municipality):
        validator = ValidatorFactory.create(
            municipality=municipality,
            name="Marcos Vera",
        )
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        decide(report, validator)

        response = detail(agent_client, report)

        validation = response.data["validation"]
        assert validation["validator"]["id"] == validator.id
        assert validation["validator"]["name"] == "Marcos Vera"
        assert validation["outcome"] == "validado"
        assert validation["decided_at"] is not None

    def test_a_rejected_report_names_the_validator_that_rejected_it(
        self,
        agent_client,
        municipality,
    ):
        """Un reporte cancelado por el validador también dice quién fue."""
        validator = ValidatorFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.CANCELADO,
            with_history=False,
        )
        decide(report, validator, Report.Status.CANCELADO, reason="No es un bache.")

        response = detail(agent_client, report)

        assert response.data["validation"]["validator"]["id"] == validator.id
        assert response.data["validation"]["outcome"] == "rechazado"

    def test_a_report_the_municipality_cancelled_has_no_validator(
        self,
        agent_client,
        municipality,
    ):
        """Cancelar desde el panel no es rechazar en terreno.

        Sale de *En proceso* y lo ejecuta un agente: mirar solo el estado de
        llegada lo haría pasar por una decisión del validador.
        """
        agent = MunicipalAgentFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.CANCELADO,
            with_history=False,
        )
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.EN_PROCESO,
            status=Report.Status.CANCELADO,
            changed_by=agent,
            reason="Duplicado.",
        )

        response = detail(agent_client, report)

        assert response.data["validation"] is None

    def test_a_pending_report_has_nobody(self, agent_client, municipality):
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
        )

        response = detail(agent_client, report)

        assert response.data["validation"] is None

    def test_reactivating_does_not_pass_the_agent_off_as_a_validator(
        self,
        agent_client,
        municipality,
    ):
        """El caso que rompe mirar solo el estado de llegada.

        ``reactivar`` también deja el reporte en *Reportado*, pero lo ejecuta un
        agente desde el panel y viniendo de *Archivado*.
        """
        agent = MunicipalAgentFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.ARCHIVADO,
            status=Report.Status.REPORTADO,
            changed_by=agent,
        )

        response = detail(agent_client, report)

        assert response.data["validation"] is None

    def test_a_reactivated_report_keeps_its_original_validator(
        self,
        agent_client,
        municipality,
    ):
        """Validado hay uno solo, aunque el reporte vuelva a pasar por Reportado."""
        validator = ValidatorFactory.create(municipality=municipality)
        agent = MunicipalAgentFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        decide(report, validator)
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.ARCHIVADO,
            status=Report.Status.REPORTADO,
            changed_by=agent,
        )

        response = detail(agent_client, report)

        assert response.data["validation"]["validator"]["id"] == validator.id

    def test_the_platform_admin_sees_it_too(self, municipality):
        """Los dos roles del panel llegan al detalle, y los dos lo necesitan."""
        validator = ValidatorFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        decide(report, validator)
        client = APIClient()
        client.force_authenticate(PlatformAdminFactory.create())

        response = detail(client, report)

        assert response.data["validation"]["validator"]["id"] == validator.id

    def test_a_deleted_validator_leaves_the_report_without_one(
        self,
        agent_client,
        municipality,
    ):
        """``changed_by`` es nulable: el campo no puede reventar por eso."""
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        decide(report, None)

        response = detail(agent_client, report)

        assert response.data["validation"]["validator"] is None
        assert response.data["validation"]["outcome"] == "validado"


class TestFilterByValidator:
    """El listado que alimenta el perfil del validador en el panel."""

    def listing(self, client: APIClient, validator):
        return client.get(f"/api/panel/reports/?validated_by={validator.id}")

    def test_lists_what_that_validator_decided(self, agent_client, municipality):
        validator = ValidatorFactory.create(municipality=municipality)
        confirmed = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        rejected = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.CANCELADO,
            with_history=False,
        )
        untouched = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
            with_history=False,
        )
        decide(confirmed, validator)
        decide(rejected, validator, Report.Status.CANCELADO, reason="No corresponde.")

        response = self.listing(agent_client, validator)

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {confirmed.id, rejected.id}
        assert untouched.id not in returned

    def test_each_row_says_what_was_decided(self, agent_client, municipality):
        validator = ValidatorFactory.create(municipality=municipality)
        rejected = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.CANCELADO,
            with_history=False,
        )
        decide(rejected, validator, Report.Status.CANCELADO, reason="No corresponde.")

        response = self.listing(agent_client, validator)

        row = response.data["results"][0]
        assert row["validation"]["outcome"] == "rechazado"
        assert row["validation"]["decided_at"] is not None

    def test_a_validated_report_cancelled_later_still_reads_as_validated(
        self,
        agent_client,
        municipality,
    ):
        """El caso que hace falta anotar la decisión.

        El reporte figura *Cancelado* igual que uno rechazado, pero este
        validador lo confirmó: fue el municipio el que lo canceló después.
        """
        validator = ValidatorFactory.create(municipality=municipality)
        agent = MunicipalAgentFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.CANCELADO,
            with_history=False,
        )
        decide(report, validator)
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.EN_PROCESO,
            status=Report.Status.CANCELADO,
            changed_by=agent,
            reason="Se resolvió por otra vía.",
        )

        response = self.listing(agent_client, validator)

        row = response.data["results"][0]
        assert row["status"] == Report.Status.CANCELADO
        assert row["validation"]["outcome"] == "validado"

    def test_without_the_filter_no_row_carries_a_decision(
        self,
        agent_client,
        municipality,
    ):
        """Sin validador por el que preguntar, no hay decisión que contar."""
        validator = ValidatorFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        decide(report, validator)

        response = agent_client.get("/api/panel/reports/")

        assert response.data["results"][0]["validation"] is None

    def test_it_does_not_cross_jurisdictions(self, agent_client, municipality):
        """Mismo criterio que el resto: se aplica sobre lo ya acotado."""
        validator = ValidatorFactory.create(municipality=municipality)
        elsewhere = ReportFactory.create(
            municipality=MunicipalityFactory.create(),
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        decide(elsewhere, validator)

        response = self.listing(agent_client, validator)

        assert response.data["results"] == []
