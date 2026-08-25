"""US-017 — alta, edición, baja y cobertura de municipalidades."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory

URL = "/api/municipalities/"

# Villa María y su vecina: centros reales, para que las distancias del test
# signifiquen algo.
VILLA_MARIA = {"latitude": -32.4103, "longitude": -63.2400}
CORDOBA_CAPITAL = {"latitude": -31.4201, "longitude": -64.1888}

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(PlatformAdminFactory.create())
    return client


def payload(**overrides) -> dict:
    return {
        "city": "Villa María",
        "province": "Córdoba",
        "coverage_radius_km": "15.00",
        **VILLA_MARIA,
        **overrides,
    }


class TestCreateMunicipality:
    def test_platform_admin_can_register_a_municipality(self, admin_client):
        response = admin_client.post(URL, payload(), format="json")

        assert response.status_code == 201
        assert Municipality.objects.filter(
            city="Villa María",
            province="Córdoba",
        ).exists()

    def test_the_coverage_area_is_stored(self, admin_client):
        response = admin_client.post(URL, payload(), format="json")

        municipality = Municipality.objects.get(pk=response.data["id"])
        assert float(municipality.coverage_radius_km) == 15.00  # noqa: PLR2004
        assert municipality.has_coverage

    @pytest.mark.parametrize(
        "missing",
        ["latitude", "longitude", "coverage_radius_km"],
    )
    def test_the_coverage_area_is_mandatory(self, admin_client, missing):
        """Sin cobertura no se sabe qué reportes le tocan: no se puede dar de alta."""
        body = payload()
        del body[missing]

        response = admin_client.post(URL, body, format="json")

        assert response.status_code == 400
        assert missing in response.data

    @pytest.mark.parametrize("radius", ["0", "-5"])
    def test_a_non_positive_radius_is_rejected(self, admin_client, radius):
        response = admin_client.post(
            URL,
            payload(coverage_radius_km=radius),
            format="json",
        )

        assert response.status_code == 400
        assert "coverage_radius_km" in response.data

    def test_duplicate_is_rejected_as_a_field_error(self, admin_client):
        MunicipalityFactory.create(city="Villa María", province="Córdoba")

        response = admin_client.post(URL, payload(), format="json")

        assert response.status_code == 400
        # El panel lo muestra debajo del input, no como toast genérico.
        assert "city" in response.data

    def test_duplicate_check_ignores_case_and_padding(self, admin_client):
        MunicipalityFactory.create(city="Villa María", province="Córdoba")

        response = admin_client.post(
            URL,
            payload(city="  villa maría ", province="córdoba"),
            format="json",
        )

        assert response.status_code == 400

    def test_the_same_city_in_another_province_is_allowed(self, admin_client):
        MunicipalityFactory.create(city="San Martín", province="Córdoba")

        response = admin_client.post(
            URL,
            payload(city="San Martín", province="Mendoza"),
            format="json",
        )

        assert response.status_code == 201


class TestCoordinatePrecision:
    def test_a_georef_centroid_is_accepted_and_rounded(self, admin_client):
        """El centroide oficial trae trece decimales; el campo guarda seis."""
        response = admin_client.post(
            URL,
            payload(latitude=-32.6303142822017, longitude=-62.6887933841481),
            format="json",
        )

        assert response.status_code == 201
        municipality = Municipality.objects.get(pk=response.data["id"])
        assert str(municipality.latitude) == "-32.630314"
        assert str(municipality.longitude) == "-62.688793"

    def test_a_coordinate_off_the_planet_is_still_rejected(self, admin_client):
        response = admin_client.post(URL, payload(latitude=91), format="json")

        assert response.status_code == 400
        assert "latitude" in response.data


class TestEditMunicipality:
    def test_the_admin_can_move_the_coverage_area(self, admin_client):
        municipality = MunicipalityFactory.create()

        response = admin_client.patch(
            f"{URL}{municipality.pk}/",
            {"coverage_radius_km": "42.50"},
            format="json",
        )

        assert response.status_code == 200
        municipality.refresh_from_db()
        assert float(municipality.coverage_radius_km) == 42.50  # noqa: PLR2004

    def test_renaming_to_an_existing_pair_is_rejected(self, admin_client):
        MunicipalityFactory.create(city="Villa María", province="Córdoba")
        other = MunicipalityFactory.create(city="Villa Nueva", province="Córdoba")

        response = admin_client.patch(
            f"{URL}{other.pk}/",
            {"city": "Villa María"},
            format="json",
        )

        assert response.status_code == 400
        assert "city" in response.data

    def test_a_municipality_can_keep_its_own_name_while_editing(self, admin_client):
        """El chequeo de duplicado no se puede disparar contra uno mismo."""
        municipality = MunicipalityFactory.create(city="Villa María", province="Córdoba")

        response = admin_client.patch(
            f"{URL}{municipality.pk}/",
            {"city": "Villa María", "coverage_radius_km": "20"},
            format="json",
        )

        assert response.status_code == 200


class TestDeleteMunicipality:
    def test_deleting_is_logical(self, admin_client):
        """Un municipio con historia no se borra: se desactiva."""
        municipality = MunicipalityFactory.create()

        response = admin_client.delete(f"{URL}{municipality.pk}/")

        assert response.status_code == 200
        municipality.refresh_from_db()
        assert municipality.is_active is False

    def test_a_deleted_municipality_leaves_the_listing(self, admin_client):
        municipality = MunicipalityFactory.create()
        admin_client.delete(f"{URL}{municipality.pk}/")

        response = admin_client.get(URL)

        assert municipality.pk not in {row["id"] for row in response.data["results"]}

    def test_registering_it_again_revives_it_with_its_history(self, admin_client):
        """Sin esto la ciudad quedaría bloqueada para siempre por la constraint."""
        from urbancheck.reports.tests.factories import ReportFactory

        municipality = MunicipalityFactory.create(
            city="Villa María",
            province="Córdoba",
        )
        ReportFactory.create(municipality=municipality)
        admin_client.delete(f"{URL}{municipality.pk}/")

        response = admin_client.post(URL, payload(coverage_radius_km="30"), format="json")

        assert response.status_code == 201
        assert response.data["id"] == municipality.pk
        municipality.refresh_from_db()
        assert municipality.is_active is True
        assert float(municipality.coverage_radius_km) == 30.00  # noqa: PLR2004
        # Sus reportes siguen colgando de él.
        assert municipality.reports.count() == 1

    def test_its_users_and_reports_survive(self, admin_client):
        municipality = MunicipalityFactory.create()
        agent = MunicipalAgentFactory.create(municipality=municipality)

        admin_client.delete(f"{URL}{municipality.pk}/")

        agent.refresh_from_db()
        assert agent.municipality == municipality


class TestListing:
    def test_each_row_carries_its_counters(self, admin_client):
        from urbancheck.reports.tests.factories import ReportFactory

        municipality = MunicipalityFactory.create()
        ReportFactory.create_batch(3, municipality=municipality)
        MunicipalAgentFactory.create(municipality=municipality)

        response = admin_client.get(URL)

        row = next(r for r in response.data["results"] if r["id"] == municipality.pk)
        assert row["report_count"] == 3  # noqa: PLR2004
        assert row["user_count"] == 1


class TestMunicipalityPermissions:
    @pytest.mark.parametrize(
        "factory",
        [UserFactory, MunicipalAgentFactory],
        ids=["citizen", "municipal_agent"],
    )
    def test_non_platform_admin_is_denied(self, factory):
        municipality = MunicipalityFactory.create()
        client = APIClient()
        client.force_authenticate(factory.create())

        assert client.get(URL).status_code == 403
        assert client.post(URL, payload(), format="json").status_code == 403
        assert client.delete(f"{URL}{municipality.pk}/").status_code == 403

    def test_anonymous_is_denied(self):
        assert APIClient().get(URL).status_code == 403
