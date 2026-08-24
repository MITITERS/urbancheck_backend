"""US-006: el scroll infinito del feed se apoya en la paginación del backend.

La app pide ``?page=N`` y sigue pidiendo mientras ``next`` no sea nulo, así que el
contrato que hay que sostener es ese: ``count``, ``next``, ``previous`` y páginas
de tamaño fijo. Sin esto el feed se queda en los primeros 20 reportes sin error
visible.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

PAGE_SIZE = settings.REST_FRAMEWORK["PAGE_SIZE"]
EXTRA = 5
TOTAL = PAGE_SIZE + EXTRA


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestFeedPagination:
    def test_first_page_is_full_and_announces_more(self, auth_client):
        client, _ = auth_client
        ReportFactory.create_batch(TOTAL)
        res = client.get("/api/reports/")
        assert res.status_code == 200
        assert res.data["count"] == TOTAL
        assert len(res.data["results"]) == PAGE_SIZE
        assert res.data["next"] is not None
        assert res.data["previous"] is None

    def test_last_page_closes_the_scroll(self, auth_client):
        client, _ = auth_client
        ReportFactory.create_batch(TOTAL)
        res = client.get("/api/reports/?page=2")
        assert res.status_code == 200
        assert len(res.data["results"]) == EXTRA
        assert res.data["next"] is None

    def test_pages_do_not_overlap(self, auth_client):
        """Un id repetido entre páginas duplicaría tarjetas en el feed."""
        client, _ = auth_client
        ReportFactory.create_batch(TOTAL)
        first = {r["id"] for r in client.get("/api/reports/").data["results"]}
        second = {r["id"] for r in client.get("/api/reports/?page=2").data["results"]}
        assert first & second == set()
        assert len(first | second) == TOTAL

    def test_order_is_newest_first_across_pages(self, auth_client):
        client, _ = auth_client
        ReportFactory.create_batch(TOTAL)
        ids = [r["id"] for r in client.get("/api/reports/").data["results"]]
        ids += [r["id"] for r in client.get("/api/reports/?page=2").data["results"]]
        expected = list(
            Report.objects.order_by("-created_at", "-id").values_list("id", flat=True),
        )
        assert ids == expected

    def test_page_beyond_the_end_returns_404(self, auth_client):
        client, _ = auth_client
        ReportFactory.create_batch(3)
        res = client.get("/api/reports/?page=99")
        assert res.status_code == 404

    def test_filters_survive_pagination(self, auth_client):
        """El scroll infinito filtrado debe seguir filtrando en la página 2."""
        client, _ = auth_client
        ReportFactory.create_batch(TOTAL, category=Report.Category.BACHE)
        ReportFactory.create_batch(3, category=Report.Category.BASURA)
        res = client.get("/api/reports/?category=bache&page=2")
        assert res.data["count"] == TOTAL
        assert all(r["category"] == "bache" for r in res.data["results"])
