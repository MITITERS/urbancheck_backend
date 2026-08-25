"""US-036 y US-037 — validación en terreno y bandeja de pendientes."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

URL = "/api/validation/reports/"

# Punto de referencia y otro a ~330 m, fuera del radio de 50 m.
HERE = {"latitude": -32.4103, "longitude": -63.2400}
NEARBY = {"latitude": -32.41035, "longitude": -63.24005}
FAR = {"latitude": -32.4133, "longitude": -63.2400}

pytestmark = pytest.mark.django_db


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def validator(municipality):
    return ValidatorFactory.create(
        municipality=municipality,
        must_change_password=False,
    )


@pytest.fixture
def validator_client(validator) -> APIClient:
    client = APIClient()
    client.force_authenticate(validator)
    return client


def pending_report(municipality, **coords) -> Report:
    return ReportFactory.create(
        municipality=municipality,
        status=Report.Status.PENDIENTE_VALIDACION,
        latitude=coords.get("latitude", HERE["latitude"]),
        longitude=coords.get("longitude", HERE["longitude"]),
    )


class TestValidateInPlace:
    def test_validating_within_the_radius_moves_it_to_reported(
        self,
        validator_client,
        municipality,
        validator,
    ):
        report = pending_report(municipality)

        response = validator_client.post(
            f"{URL}{report.id}/validate/",
            NEARBY,
            format="json",
        )

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.status == Report.Status.REPORTADO
        entry = ReportStatusHistory.objects.filter(report=report).first()
        assert entry.changed_by == validator
        assert entry.previous_status == Report.Status.PENDIENTE_VALIDACION

    def test_validating_from_far_away_is_rejected_with_the_real_distance(
        self,
        validator_client,
        municipality,
    ):
        report = pending_report(municipality)

        response = validator_client.post(
            f"{URL}{report.id}/validate/",
            FAR,
            format="json",
        )

        assert response.status_code == 400
        assert response.data["code"] == "too_far"
        # El móvil necesita el número para decir "estás a X metros".
        assert response.data["distance_meters"] > response.data["radius_meters"]
        report.refresh_from_db()
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    def test_without_coordinates_the_action_is_refused(
        self,
        validator_client,
        municipality,
    ):
        report = pending_report(municipality)

        response = validator_client.post(f"{URL}{report.id}/validate/", {}, format="json")

        assert response.status_code == 400
        report.refresh_from_db()
        assert report.status == Report.Status.PENDIENTE_VALIDACION

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
    def test_a_report_that_is_not_pending_cannot_be_validated(
        self,
        validator_client,
        municipality,
        status,
    ):
        report = ReportFactory.create(
            municipality=municipality,
            status=status,
            **HERE,
        )

        response = validator_client.post(
            f"{URL}{report.id}/validate/",
            NEARBY,
            format="json",
        )

        assert response.status_code == 409
        report.refresh_from_db()
        assert report.status == status

    def test_the_radius_comes_from_configuration(
        self,
        validator_client,
        municipality,
        settings,
    ):
        report = pending_report(municipality)
        # Con un radio amplio, el mismo punto lejano pasa a estar dentro.
        settings.VALIDATION_RADIUS_METERS = 1000

        response = validator_client.post(
            f"{URL}{report.id}/validate/",
            FAR,
            format="json",
        )

        assert response.status_code == 200


class TestReject:
    def test_rejecting_cancels_the_report(self, validator_client, municipality):
        report = pending_report(municipality)

        response = validator_client.post(
            f"{URL}{report.id}/reject/",
            {**NEARBY, "reason": "No hay ningún bache en el lugar"},
            format="json",
        )

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.status == Report.Status.CANCELADO

    def test_rejecting_without_a_reason_is_refused(
        self,
        validator_client,
        municipality,
    ):
        report = pending_report(municipality)

        response = validator_client.post(
            f"{URL}{report.id}/reject/",
            NEARBY,
            format="json",
        )

        assert response.status_code == 400
        report.refresh_from_db()
        assert report.status == Report.Status.PENDIENTE_VALIDACION

    def test_the_rejection_reason_lands_in_the_history(
        self,
        validator_client,
        municipality,
    ):
        report = pending_report(municipality)

        validator_client.post(
            f"{URL}{report.id}/reject/",
            {**NEARBY, "reason": "Duplicado del reporte #12"},
            format="json",
        )

        entry = ReportStatusHistory.objects.filter(report=report).first()
        assert entry.reason == "Duplicado del reporte #12"


class TestWhoCanValidate:
    @pytest.mark.parametrize(
        "factory",
        [UserFactory, MunicipalAgentFactory],
        ids=["citizen", "municipal_agent"],
    )
    def test_other_roles_are_denied(self, factory, municipality):
        report = pending_report(municipality)
        client = APIClient()
        client.force_authenticate(factory.create())

        assert client.get(URL).status_code == 403
        assert (
            client.post(f"{URL}{report.id}/validate/", NEARBY, format="json").status_code
            == 403
        )

    def test_a_deactivated_validator_is_denied(self, municipality):
        validator = ValidatorFactory.create(
            municipality=municipality,
            must_change_password=False,
            is_validator_active=False,
        )
        client = APIClient()
        client.force_authenticate(validator)

        assert client.get(URL).status_code == 403

    def test_a_validator_with_a_temporary_password_is_denied(self, municipality):
        validator = ValidatorFactory.create(
            municipality=municipality,
            must_change_password=True,
        )
        client = APIClient()
        client.force_authenticate(validator)

        assert client.get(URL).status_code == 403

    def test_a_validator_of_another_municipality_cannot_validate(
        self,
        validator_client,
    ):
        """La capa de jurisdicción ya lo cubre, pero conviene testearlo explícito."""
        foreign = pending_report(MunicipalityFactory.create())

        response = validator_client.post(
            f"{URL}{foreign.id}/validate/",
            NEARBY,
            format="json",
        )

        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.status == Report.Status.PENDIENTE_VALIDACION


class TestPendingInbox:
    def test_only_pending_reports_of_my_municipality_are_listed(
        self,
        validator_client,
        municipality,
    ):
        mine = pending_report(municipality)
        ReportFactory.create(municipality=municipality, status=Report.Status.REPORTADO)
        foreign = pending_report(MunicipalityFactory.create())

        response = validator_client.get(URL)

        ids = {row["id"] for row in response.data["results"]}
        assert ids == {mine.id}
        assert foreign.id not in ids

    def test_it_is_ordered_by_proximity(self, validator_client, municipality):
        near = pending_report(municipality, **NEARBY)
        far = pending_report(municipality, **FAR)

        response = validator_client.get(URL, HERE)

        assert [row["id"] for row in response.data["results"]] == [near.id, far.id]

    def test_the_distance_travels_with_each_row(self, validator_client, municipality):
        pending_report(municipality, **NEARBY)

        response = validator_client.get(URL, HERE)

        assert response.data["results"][0]["distance_meters"] < 50  # noqa: PLR2004

    def test_it_works_without_coordinates(self, validator_client, municipality):
        """La pantalla tiene que funcionar sin permiso de ubicación."""
        pending_report(municipality)

        response = validator_client.get(URL)

        assert response.status_code == 200
        assert response.data["results"][0]["distance_meters"] is None

    def test_an_empty_inbox_is_not_an_error(self, validator_client):
        response = validator_client.get(URL)

        assert response.status_code == 200
        assert response.data["count"] == 0

    def test_a_validated_report_leaves_the_inbox(self, validator_client, municipality):
        report = pending_report(municipality)

        validator_client.post(f"{URL}{report.id}/validate/", NEARBY, format="json")
        response = validator_client.get(URL)

        assert report.id not in {row["id"] for row in response.data["results"]}
