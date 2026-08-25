"""El administrador de la plataforma mira los reportes de un municipio.

Es la única lectura de reportes que cruza jurisdicciones, y está acotada al
administrador: el agente municipal sigue viendo solo lo suyo (US-034).
"""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(PlatformAdminFactory.create())
    return client


@pytest.fixture
def two_cities():
    first = MunicipalityFactory.create(city="Villa María")
    second = MunicipalityFactory.create(city="Villa Nueva")
    return first, second


def reports_url(pk: int) -> str:
    return f"/api/municipalities/{pk}/reports/"


def map_url(pk: int) -> str:
    return f"/api/municipalities/{pk}/reports/map/"


class TestReportsOfOneMunicipality:
    def test_only_the_reports_of_that_municipality_are_listed(
        self,
        admin_client,
        two_cities,
    ):
        first, second = two_cities
        mine = ReportFactory.create_batch(3, municipality=first)
        ReportFactory.create_batch(2, municipality=second)

        response = admin_client.get(reports_url(first.pk))

        assert response.status_code == 200
        assert {row["id"] for row in response.data["results"]} == {r.id for r in mine}

    def test_the_listing_accepts_the_same_filters_as_the_panel(
        self,
        admin_client,
        two_cities,
    ):
        first, _ = two_cities
        resolved = ReportFactory.create(
            municipality=first,
            status=Report.Status.RESUELTO,
        )
        ReportFactory.create(municipality=first, status=Report.Status.REPORTADO)

        response = admin_client.get(
            reports_url(first.pk),
            {"status": Report.Status.RESUELTO},
        )

        assert [row["id"] for row in response.data["results"]] == [resolved.id]

    def test_the_listing_is_paginated(self, admin_client, two_cities, settings):
        first, _ = two_cities
        ReportFactory.create_batch(25, municipality=first)

        response = admin_client.get(reports_url(first.pk))

        assert response.data["count"] == 25  # noqa: PLR2004
        assert len(response.data["results"]) == settings.REST_FRAMEWORK["PAGE_SIZE"]


class TestMarkers:
    def test_the_map_returns_every_marker_unpaginated(self, admin_client, two_cities):
        first, _ = two_cities
        ReportFactory.create_batch(25, municipality=first)

        response = admin_client.get(map_url(first.pk))

        assert len(response.data["results"]) == 25  # noqa: PLR2004

    def test_reports_without_coordinates_are_left_out(self, admin_client, two_cities):
        first, _ = two_cities
        ReportFactory.create(municipality=first, latitude=None, longitude=None)
        located = ReportFactory.create(municipality=first)

        response = admin_client.get(map_url(first.pk))

        assert [row["id"] for row in response.data["results"]] == [located.id]

    def test_markers_of_another_municipality_never_appear(
        self,
        admin_client,
        two_cities,
    ):
        first, second = two_cities
        foreign = ReportFactory.create(municipality=second)
        ReportFactory.create(municipality=first)

        response = admin_client.get(map_url(first.pk))

        assert foreign.id not in {row["id"] for row in response.data["results"]}


class TestPermissions:
    @pytest.mark.parametrize(
        "factory",
        [UserFactory, MunicipalAgentFactory],
        ids=["citizen", "municipal_agent"],
    )
    def test_only_the_platform_admin_can_read_them(self, factory, two_cities):
        first, _ = two_cities
        client = APIClient()
        client.force_authenticate(factory.create())

        assert client.get(reports_url(first.pk)).status_code == 403
        assert client.get(map_url(first.pk)).status_code == 403

    def test_an_agent_cannot_use_it_to_reach_another_municipality(self, two_cities):
        """La vía del administrador no es un atajo para saltear la jurisdicción."""
        first, second = two_cities
        ReportFactory.create(municipality=second)
        client = APIClient()
        client.force_authenticate(MunicipalAgentFactory.create(municipality=first))

        assert client.get(reports_url(second.pk)).status_code == 403
