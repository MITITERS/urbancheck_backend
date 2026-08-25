"""US-012 — listado del panel: filtros, orden y paginación."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory

URL = "/api/panel/reports/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def agent_client(municipality) -> APIClient:
    client = APIClient()
    client.force_authenticate(MunicipalAgentFactory.create(municipality=municipality))
    return client


def ids_in(response) -> list[int]:
    return [row["id"] for row in response.data["results"]]


class TestListingPayload:
    def test_row_carries_what_the_table_needs(self, agent_client, municipality):
        report = ReportFactory.create(
            municipality=municipality,
            address="Bv. España 100",
        )
        LikeFactory.create(report=report)

        row = agent_client.get(URL).data["results"][0]

        assert row["id"] == report.id
        assert row["category"] == report.category
        assert row["status"] == report.status
        assert row["address"] == "Bv. España 100"
        assert row["like_count"] == 1
        assert "created_at" in row
        # US-028 no está en este sprint: la columna viaja siempre vacía.
        assert row["operative_area"] is None

    def test_the_endpoint_without_parameters_returns_every_status(
        self,
        agent_client,
        municipality,
    ):
        """El default de estados lo aplica el frontend, no el backend."""
        for status in Report.Status:
            ReportFactory.create(municipality=municipality, status=status)

        response = agent_client.get(URL)

        returned = {row["status"] for row in response.data["results"]}
        assert returned == {status.value for status in Report.Status}


class TestStatusFilter:
    def test_filters_by_a_single_status(self, agent_client, municipality):
        wanted = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.EN_PROCESO,
        )
        ReportFactory.create(municipality=municipality, status=Report.Status.RESUELTO)

        response = agent_client.get(URL, {"status": Report.Status.EN_PROCESO})

        assert ids_in(response) == [wanted.id]

    def test_several_statuses_combine_with_or(self, agent_client, municipality):
        pending = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
        )
        reported = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
        )
        ReportFactory.create(municipality=municipality, status=Report.Status.ARCHIVADO)

        response = agent_client.get(
            URL,
            {"status": f"{Report.Status.PENDIENTE_VALIDACION},{Report.Status.REPORTADO}"},
        )

        assert set(ids_in(response)) == {pending.id, reported.id}

    @pytest.mark.parametrize("status", [s.value for s in Report.Status])
    def test_every_one_of_the_six_statuses_is_filterable(
        self,
        agent_client,
        municipality,
        status,
    ):
        report = ReportFactory.create(municipality=municipality, status=status)

        response = agent_client.get(URL, {"status": status})

        assert ids_in(response) == [report.id]


class TestCategoryAndZoneFilters:
    def test_filters_by_category(self, agent_client, municipality):
        bache = ReportFactory.create(
            municipality=municipality,
            category=Report.Category.BACHE,
        )
        ReportFactory.create(
            municipality=municipality,
            category=Report.Category.BASURA,
        )

        response = agent_client.get(URL, {"category": Report.Category.BACHE})

        assert ids_in(response) == [bache.id]

    def test_zone_is_a_text_search_over_the_address(self, agent_client, municipality):
        """No existe una entidad Zona: se filtra por texto de dirección."""
        centro = ReportFactory.create(
            municipality=municipality,
            address="Bv. España 100, Centro",
        )
        ReportFactory.create(municipality=municipality, address="Barrio Rivadavia 200")

        response = agent_client.get(URL, {"zone": "centro"})

        assert ids_in(response) == [centro.id]


class TestDateRangeFilter:
    def test_filters_by_creation_range(self, agent_client, municipality):
        old = ReportFactory.create(municipality=municipality)
        recent = ReportFactory.create(municipality=municipality)
        Report.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )

        response = agent_client.get(
            URL,
            {"created_from": (timezone.now() - timedelta(days=2)).date().isoformat()},
        )

        assert ids_in(response) == [recent.id]


class TestCombinedFilters:
    def test_filters_are_combined_with_and(self, agent_client, municipality):
        match = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            category=Report.Category.BACHE,
            address="Centro",
        )
        # Cada uno falla en un criterio distinto.
        ReportFactory.create(
            municipality=municipality,
            status=Report.Status.RESUELTO,
            category=Report.Category.BACHE,
            address="Centro",
        )
        ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            category=Report.Category.BASURA,
            address="Centro",
        )
        ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            category=Report.Category.BACHE,
            address="Rivadavia",
        )

        response = agent_client.get(
            URL,
            {
                "status": Report.Status.REPORTADO,
                "category": Report.Category.BACHE,
                "zone": "centro",
            },
        )

        assert ids_in(response) == [match.id]


class TestOrdering:
    def test_orders_by_like_count_descending(self, agent_client, municipality):
        popular = ReportFactory.create(municipality=municipality)
        quiet = ReportFactory.create(municipality=municipality)
        LikeFactory.create_batch(3, report=popular)
        LikeFactory.create(report=quiet)

        response = agent_client.get(URL, {"ordering": "-like_count"})

        assert ids_in(response) == [popular.id, quiet.id]

    def test_orders_by_like_count_ascending(self, agent_client, municipality):
        popular = ReportFactory.create(municipality=municipality)
        quiet = ReportFactory.create(municipality=municipality)
        LikeFactory.create_batch(3, report=popular)

        response = agent_client.get(URL, {"ordering": "like_count"})

        assert ids_in(response) == [quiet.id, popular.id]

    def test_orders_by_creation_date(self, agent_client, municipality):
        first = ReportFactory.create(municipality=municipality)
        second = ReportFactory.create(municipality=municipality)

        ascending = agent_client.get(URL, {"ordering": "created_at"})
        descending = agent_client.get(URL, {"ordering": "-created_at"})

        assert ids_in(ascending) == [first.id, second.id]
        assert ids_in(descending) == [second.id, first.id]


class TestPagination:
    def test_the_listing_is_paginated(self, agent_client, municipality, settings):
        ReportFactory.create_batch(25, municipality=municipality)

        response = agent_client.get(URL)

        assert response.data["count"] == 25
        assert len(response.data["results"]) == settings.REST_FRAMEWORK["PAGE_SIZE"]
        assert response.data["next"] is not None

    def test_second_page_returns_the_rest(self, agent_client, municipality):
        ReportFactory.create_batch(25, municipality=municipality)

        response = agent_client.get(URL, {"page": 2})

        assert len(response.data["results"]) == 5


class TestFiltersNeverCrossJurisdiction:
    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"status": "reportado"},
            {"category": "bache"},
            {"ordering": "-like_count"},
            {"zone": "centro"},
        ],
    )
    def test_no_parameter_combination_leaks_another_municipality(
        self,
        agent_client,
        municipality,
        params,
    ):
        ReportFactory.create(
            municipality=municipality,
            status=Report.Status.REPORTADO,
            category=Report.Category.BACHE,
            address="Centro",
        )
        foreign = ReportFactory.create_batch(
            3,
            municipality=MunicipalityFactory.create(),
            status=Report.Status.REPORTADO,
            category=Report.Category.BACHE,
            address="Centro",
        )

        response = agent_client.get(URL, params)

        returned = set(ids_in(response))
        assert returned.isdisjoint({r.id for r in foreign})
