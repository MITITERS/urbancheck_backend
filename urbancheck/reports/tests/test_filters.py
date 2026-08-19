"""US-006 (filtros del feed) y US-020 (búsqueda por palabra clave o zona)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def ids_of(response):
    return {r["id"] for r in response.data["results"]}


@pytest.mark.django_db
class TestCategoryAndStatusFilters:
    def test_filter_by_single_category(self, auth_client):
        client, _ = auth_client
        bache = ReportFactory.create(category=Report.Category.BACHE)
        ReportFactory.create(category=Report.Category.BASURA)
        res = client.get("/api/reports/?category=bache")
        assert res.status_code == 200
        assert ids_of(res) == {bache.id}

    def test_filter_by_several_categories(self, auth_client):
        client, _ = auth_client
        bache = ReportFactory.create(category=Report.Category.BACHE)
        basura = ReportFactory.create(category=Report.Category.BASURA)
        ReportFactory.create(category=Report.Category.VEREDA)
        res = client.get("/api/reports/?category=bache,basura")
        assert ids_of(res) == {bache.id, basura.id}

    def test_filter_by_status(self, auth_client):
        client, _ = auth_client
        resuelto = ReportFactory.create(status=Report.Status.RESUELTO)
        ReportFactory.create(status=Report.Status.REPORTADO)
        res = client.get("/api/reports/?status=resuelto")
        assert ids_of(res) == {resuelto.id}

    def test_combined_category_and_status(self, auth_client):
        client, _ = auth_client
        match = ReportFactory.create(
            category=Report.Category.BACHE, status=Report.Status.RESUELTO
        )
        ReportFactory.create(category=Report.Category.BACHE, status=Report.Status.REPORTADO)
        ReportFactory.create(category=Report.Category.BASURA, status=Report.Status.RESUELTO)
        res = client.get("/api/reports/?category=bache&status=resuelto")
        assert ids_of(res) == {match.id}

    def test_unknown_value_is_ignored(self, auth_client):
        """Un parámetro mal escrito no debe romper el feed ni vaciarlo."""
        client, _ = auth_client
        ReportFactory.create_batch(2)
        res = client.get("/api/reports/?category=noexiste")
        assert res.status_code == 200
        assert res.data["count"] == 2


@pytest.mark.django_db
class TestSearch:
    def test_search_by_description(self, auth_client):
        client, _ = auth_client
        target = ReportFactory.create(description="Semáforo roto en la esquina")
        ReportFactory.create(description="Basura acumulada")
        res = client.get("/api/reports/?search=roto")
        assert ids_of(res) == {target.id}

    def test_search_by_address(self, auth_client):
        client, _ = auth_client
        target = ReportFactory.create(
            description="Bache profundo", address="Av. Rivadavia 4500, Caballito"
        )
        ReportFactory.create(description="Otro bache", address="Calle Falsa 123, Palermo")
        res = client.get("/api/reports/?search=Caballito")
        assert ids_of(res) == {target.id}

    def test_search_by_category_label_ignores_accents(self, auth_client):
        client, _ = auth_client
        target = ReportFactory.create(
            category=Report.Category.SEMAFORO, description="Luz intermitente"
        )
        ReportFactory.create(category=Report.Category.BACHE, description="Pozo grande")
        res = client.get("/api/reports/?search=semáforo")
        assert ids_of(res) == {target.id}

    def test_search_without_results(self, auth_client):
        client, _ = auth_client
        ReportFactory.create(description="Bache en la vereda")
        res = client.get("/api/reports/?search=zzzznoexiste")
        assert res.status_code == 200
        assert res.data["count"] == 0
        assert res.data["results"] == []

    def test_q_alias_works(self, auth_client):
        client, _ = auth_client
        target = ReportFactory.create(description="Poste caído")
        ReportFactory.create(description="Basura")
        res = client.get("/api/reports/?q=poste")
        assert ids_of(res) == {target.id}
