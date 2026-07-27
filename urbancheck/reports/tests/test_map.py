"""US-010: endpoint de marcadores del mapa interactivo."""

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
class TestReportMap:
    def test_returns_markers_with_coordinates(self, auth_client):
        client, _ = auth_client
        report = ReportFactory.create(latitude="-34.603722", longitude="-58.381592")
        res = client.get("/api/reports/map/")
        assert res.status_code == 200
        marker = next(r for r in res.data["results"] if r["id"] == report.id)
        assert marker["latitude"] is not None
        assert marker["longitude"] is not None

    def test_marker_payload_supports_popup(self, auth_client):
        """El popup necesita foto en miniatura, categoría y estado (US-010)."""
        client, _ = auth_client
        ReportFactory.create(category=Report.Category.BACHE, status=Report.Status.REPORTADO)
        res = client.get("/api/reports/map/")
        marker = res.data["results"][0]
        assert set(marker) == {
            "id",
            "photo",
            "category",
            "status",
            "latitude",
            "longitude",
            "address",
            "like_count",
        }

    def test_excludes_reports_without_coordinates(self, auth_client):
        client, _ = auth_client
        sin_coords = ReportFactory.create(
            latitude=None, longitude=None, address="Sin geocodificar"
        )
        res = client.get("/api/reports/map/")
        assert sin_coords.id not in ids_of(res)

    @pytest.mark.parametrize(
        "inactive_status", [Report.Status.CANCELADO, Report.Status.ARCHIVADO]
    )
    def test_excludes_inactive_reports(self, auth_client, inactive_status):
        client, _ = auth_client
        inactivo = ReportFactory.create(status=inactive_status)
        activo = ReportFactory.create(status=Report.Status.REPORTADO)
        res = client.get("/api/reports/map/")
        assert inactivo.id not in ids_of(res)
        assert activo.id in ids_of(res)

    def test_respects_category_filter(self, auth_client):
        client, _ = auth_client
        bache = ReportFactory.create(category=Report.Category.BACHE)
        ReportFactory.create(category=Report.Category.BASURA)
        res = client.get("/api/reports/map/?category=bache")
        assert ids_of(res) == {bache.id}

    def test_respects_status_filter(self, auth_client):
        client, _ = auth_client
        resuelto = ReportFactory.create(status=Report.Status.RESUELTO)
        ReportFactory.create(status=Report.Status.REPORTADO)
        res = client.get("/api/reports/map/?status=resuelto")
        assert ids_of(res) == {resuelto.id}

    def test_is_not_paginated(self, auth_client):
        """El mapa necesita todos los marcadores, no una página del feed."""
        client, _ = auth_client
        ReportFactory.create_batch(25)
        res = client.get("/api/reports/map/")
        assert "count" not in res.data
        assert len(res.data["results"]) == 25
