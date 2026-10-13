"""US-028 — asignar un reporte a un área operativa municipal."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportAreaAssignment
from urbancheck.reports.services import AreaRequiredError
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import TRANSITIONS
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


def url(report_id: int, suffix: str = "") -> str:
    return f"/api/panel/reports/{report_id}/{suffix}"


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def area(municipality):
    return OperationalAreaFactory.create(municipality=municipality)


@pytest.fixture
def agent(municipality):
    return MunicipalAgentFactory.create(municipality=municipality)


@pytest.fixture
def client(agent) -> APIClient:
    api = APIClient()
    api.force_authenticate(agent)
    return api


@pytest.fixture
def reported(municipality):
    return ReportFactory.create(
        municipality=municipality,
        status=Report.Status.REPORTADO,
    )


def in_progress(municipality, area):
    return ReportFactory.create(
        municipality=municipality,
        status=Report.Status.EN_PROCESO,
        operational_area=area,
    )


class TestAssignmentStartsTheWork:
    def test_it_links_the_area_and_moves_to_in_progress(
        self,
        client,
        reported,
        area,
        agent,
    ):
        """Escenario 1: el vínculo, el estado y la traza, en un solo paso."""
        response = client.post(
            url(reported.pk, "process/"),
            {"area_id": area.pk},
            format="json",
        )

        assert response.status_code == HTTP_OK
        reported.refresh_from_db()
        assert reported.status == Report.Status.EN_PROCESO
        assert reported.operational_area == area
        assert reported.area_assigned_at is not None

        assignment = ReportAreaAssignment.objects.get(report=reported)
        assert assignment.previous_area is None
        assert assignment.area == area
        assert assignment.assigned_by == agent

    def test_the_area_is_mandatory(self, client, reported):
        """Escenario 2."""
        response = client.post(url(reported.pk, "process/"), {}, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        reported.refresh_from_db()
        assert reported.status == Report.Status.REPORTADO

    def test_an_explicit_null_area_is_also_rejected(self, client, reported):
        response = client.post(
            url(reported.pk, "process/"),
            {"area_id": None},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST

    def test_an_inactive_area_cannot_receive_new_reports(
        self,
        client,
        reported,
        municipality,
    ):
        """Escenario 3, por el reverso: el desplegable solo ofrece activas."""
        inactive = OperationalAreaFactory.create(
            municipality=municipality,
            is_active=False,
        )

        response = client.post(
            url(reported.pk, "process/"),
            {"area_id": inactive.pk},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert "area_id" in response.data

    def test_a_report_pending_validation_cannot_be_assigned(
        self,
        client,
        municipality,
        area,
    ):
        """Escenario 7."""
        pending = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
        )

        response = client.post(
            url(pending.pk, "process/"),
            {"area_id": area.pk},
            format="json",
        )

        assert response.status_code == HTTP_CONFLICT
        pending.refresh_from_db()
        assert pending.operational_area is None

    def test_an_area_of_another_municipality_fails_as_a_field_error(
        self,
        client,
        reported,
    ):
        """Escenario 10: 400 sobre el campo, no un 404 del reporte."""
        foreign = OperationalAreaFactory.create(
            municipality=MunicipalityFactory.create(),
        )

        response = client.post(
            url(reported.pk, "process/"),
            {"area_id": foreign.pk},
            format="json",
        )

        assert response.status_code == HTTP_BAD_REQUEST
        assert "area_id" in response.data
        reported.refresh_from_db()
        assert reported.status == Report.Status.REPORTADO
        assert reported.operational_area is None


class TestReassignment:
    def test_it_keeps_the_state_and_records_the_change(
        self,
        client,
        municipality,
        area,
        agent,
    ):
        """Escenario 5."""
        report = in_progress(municipality, area)
        destination = OperationalAreaFactory.create(municipality=municipality)

        response = client.post(
            url(report.pk, "assign-area/"),
            {"area_id": destination.pk},
            format="json",
        )

        assert response.status_code == HTTP_OK
        report.refresh_from_db()
        assert report.status == Report.Status.EN_PROCESO
        assert report.operational_area == destination

        assignment = ReportAreaAssignment.objects.filter(report=report).latest("id")
        assert assignment.previous_area == area
        assert assignment.area == destination
        assert assignment.assigned_by == agent

    def test_it_cannot_be_used_to_unassign(self, client, municipality, area):
        """Escenario 6: sin área nueva, no hay operación."""
        report = in_progress(municipality, area)

        response = client.post(url(report.pk, "assign-area/"), {}, format="json")

        assert response.status_code == HTTP_BAD_REQUEST
        report.refresh_from_db()
        assert report.operational_area == area
        assert report.status == Report.Status.EN_PROCESO

    @pytest.mark.parametrize(
        "status",
        [
            Report.Status.PENDIENTE_VALIDACION,
            Report.Status.REPORTADO,
            Report.Status.RESUELTO,
            Report.Status.CANCELADO,
            Report.Status.ARCHIVADO,
        ],
    )
    def test_it_only_works_while_the_report_is_in_progress(
        self,
        client,
        municipality,
        area,
        status,
    ):
        """Escenarios 7 y 8: fuera de gestión el área no se toca."""
        report = ReportFactory.create(municipality=municipality, status=status)

        response = client.post(
            url(report.pk, "assign-area/"),
            {"area_id": area.pk},
            format="json",
        )

        assert response.status_code == HTTP_CONFLICT

    def test_a_deactivated_area_keeps_the_reports_it_already_had(
        self,
        client,
        municipality,
        area,
    ):
        """Escenario 9."""
        report = in_progress(municipality, area)
        area.is_active = False
        area.save(update_fields=["is_active"])

        detail = client.get(url(report.pk)).data

        assert detail["operational_area"]["id"] == area.pk
        assert detail["operational_area"]["is_active"] is False

    def test_another_municipality_answers_404(self, client, area):
        foreign = ReportFactory.create(
            municipality=MunicipalityFactory.create(),
            status=Report.Status.EN_PROCESO,
        )

        response = client.post(
            url(foreign.pk, "assign-area/"),
            {"area_id": area.pk},
            format="json",
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestVisibility:
    def test_the_area_shows_in_the_panel_listing(self, client, municipality, area):
        """Escenario 11."""
        in_progress(municipality, area)

        row = client.get("/api/panel/reports/").data["results"][0]

        assert row["operative_area"]["id"] == area.pk
        assert row["operative_area"]["name"] == area.name

    def test_the_assignment_history_travels_in_the_detail(
        self,
        client,
        municipality,
        area,
        reported,
    ):
        client.post(url(reported.pk, "process/"), {"area_id": area.pk}, format="json")
        destination = OperationalAreaFactory.create(municipality=municipality)
        client.post(
            url(reported.pk, "assign-area/"),
            {"area_id": destination.pk},
            format="json",
        )

        assignments = client.get(url(reported.pk)).data["area_assignments"]

        assert len(assignments) == 2
        assert assignments[0]["area"]["id"] == destination.pk
        assert assignments[0]["previous_area"]["id"] == area.pk

    def test_the_process_action_declares_that_it_needs_an_area(self, client, reported):
        """El panel abre el diálogo con selector porque el backend lo dice."""
        transitions = client.get(url(reported.pk)).data["available_transitions"]

        process = next(t for t in transitions if t["operation"] == "procesar")
        assert process["requires_area"] is True


class TestThereIsNoOtherWayIn:
    def test_no_declared_transition_reaches_in_progress_without_an_area(self):
        """La garantía central de la historia, comprobada sobre la tabla.

        Toda transición que deja un reporte *En proceso* o bien exige el área,
        o bien sale de un estado al que solo se llega **teniéndola** — que es el
        caso de la apelación de US-048, que reabre conservando el área que el
        reporte ya tenía. Comprobar solo ``requires_area`` dejaría pasar una
        transición nueva desde un estado sin área garantizada.
        """
        # Estados desde los que un reporte ya tiene área sí o sí: se llega a
        # ellos pasando por ``procesar``, que la exige.
        with_area = {
            Report.Status.EN_PROCESO,
            Report.Status.RESUELTO_PENDIENTE,
        }
        entries = [t for t in TRANSITIONS if t.target == Report.Status.EN_PROCESO]

        assert entries
        assert all(t.requires_area or t.source in with_area for t in entries)

    def test_the_domain_layer_refuses_too(self, municipality, agent, reported):
        """Ni siquiera llamando al servicio directamente desde el shell."""
        with pytest.raises(AreaRequiredError):
            apply_transition(
                reported,
                "procesar",
                actor=Actor.MUNICIPAL_AGENT,
                changed_by=agent,
            )

        reported.refresh_from_db()
        assert reported.status == Report.Status.REPORTADO

    def test_the_state_change_and_the_assignment_share_one_transaction(
        self,
        client,
        reported,
        area,
    ):
        """No puede existir un reporte En proceso sin asignación registrada."""
        client.post(url(reported.pk, "process/"), {"area_id": area.pk}, format="json")

        in_process = Report.objects.filter(status=Report.Status.EN_PROCESO)
        for report in in_process:
            assert report.operational_area_id is not None
            assert ReportAreaAssignment.objects.filter(report=report).exists()
