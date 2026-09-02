"""El panel elige cuántas filas por página (``?page_size=``).

Cuántas filas conviene ver depende de quién mira y de qué está haciendo, así
que el tamaño lo decide el usuario y no una constante del servidor. El tope
existe porque el parámetro llega del cliente.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.api.pagination import PanelPagination
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory

pytestmark = pytest.mark.django_db

URL = "/api/panel/reports/"
DEFAULT_PAGE_SIZE = 20


@pytest.fixture
def municipality():
    return MunicipalityFactory.create()


@pytest.fixture
def agent_client(municipality) -> APIClient:
    client = APIClient()
    client.force_authenticate(MunicipalAgentFactory.create(municipality=municipality))
    return client


@pytest.fixture
def many_reports(municipality):
    return ReportFactory.create_batch(25, municipality=municipality)


class TestPageSize:
    def test_without_the_parameter_it_keeps_the_default(
        self,
        agent_client,
        many_reports,
    ):
        response = agent_client.get(URL)

        assert len(response.data["results"]) == DEFAULT_PAGE_SIZE

    @pytest.mark.parametrize("size", [10, 50])
    def test_the_panel_chooses_how_many_rows(self, agent_client, many_reports, size):
        response = agent_client.get(URL, {"page_size": size})

        assert len(response.data["results"]) == min(size, len(many_reports))

    def test_the_count_is_the_total_and_not_the_page(self, agent_client, many_reports):
        """El paginado dice «1–10 de 25»: el total no depende del tamaño."""
        response = agent_client.get(URL, {"page_size": 10})

        assert response.data["count"] == len(many_reports)

    def test_it_is_capped(self, agent_client, many_reports):
        """Sin tope, un `page_size` enorme trae la tabla entera a memoria."""
        response = agent_client.get(URL, {"page_size": 100_000})

        assert len(response.data["results"]) <= PanelPagination.max_page_size

    def test_an_unreadable_size_falls_back_to_the_default(
        self,
        agent_client,
        many_reports,
    ):
        """Un valor basura no puede tumbar el listado."""
        response = agent_client.get(URL, {"page_size": "muchas"})

        assert response.status_code == 200
        assert len(response.data["results"]) == DEFAULT_PAGE_SIZE
