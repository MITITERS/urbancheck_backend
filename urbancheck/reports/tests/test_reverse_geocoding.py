"""Geocodificación inversa: un reporte creado por GPS debe quedar buscable por zona.

Sin dirección resuelta, la búsqueda por calle, barrio o localidad (US-020) nunca
encuentra los reportes que llegaron solo con coordenadas.
"""

from __future__ import annotations

import io

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.reports.geocoding import reverse_geocode
from urbancheck.reports.models import Report
from urbancheck.users.tests.factories import UserFactory

ADDRESS = "63, Rivadavia, Centro Sur, Villa María, Córdoba, Argentina"


def make_image_file(name="rev.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), color=(1, 2, 3)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def nominatim_reverse(monkeypatch):
    """Simula la respuesta de Nominatim y expone los parámetros recibidos."""
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params})
        return FakeResponse({"display_name": ADDRESS})

    monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", fake_get)
    cache.clear()
    return calls


@pytest.mark.django_db
class TestReverseGeocode:
    def test_returns_address(self, nominatim_reverse):
        assert reverse_geocode("-32.415620", "-63.240000") == ADDRESS

    def test_sends_coordinates_to_nominatim(self, nominatim_reverse):
        reverse_geocode("-32.415620", "-63.240000")
        params = nominatim_reverse[0]["params"]
        assert params["lat"] == "-32.415620"
        assert params["lon"] == "-63.240000"

    def test_result_is_cached(self, nominatim_reverse):
        reverse_geocode("-32.415620", "-63.240000")
        reverse_geocode("-32.415620", "-63.240000")
        assert len(nominatim_reverse) == 1

    def test_missing_coordinates_returns_empty(self, nominatim_reverse):
        assert reverse_geocode(None, None) == ""
        assert nominatim_reverse == []

    def test_network_error_returns_empty(self, monkeypatch):
        import requests

        def boom(*args, **kwargs):
            raise requests.RequestException("sin red")

        monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", boom)
        cache.clear()
        assert reverse_geocode("-32.4", "-63.2") == ""


@pytest.mark.django_db
class TestCreateResolvesAddress:
    def _create(self, client, **extra):
        data = {
            "photo": make_image_file(),
            "description": "Bache profundo",
            "category": "bache",
            **extra,
        }
        return client.post("/api/reports/", data=data, format="multipart")

    def test_gps_report_gets_address(self, auth_client, nominatim_reverse):
        client, _ = auth_client
        res = self._create(client, latitude="-32.415620", longitude="-63.240000")
        assert res.status_code == 201
        assert Report.objects.get(id=res.data["id"]).address == ADDRESS

    def test_report_becomes_searchable_by_zone(self, auth_client, nominatim_reverse):
        """El objetivo real: que la búsqueda por localidad lo encuentre."""
        client, _ = auth_client
        res = self._create(client, latitude="-32.415620", longitude="-63.240000")
        found = client.get("/api/reports/?search=Villa María")
        assert res.data["id"] in {r["id"] for r in found.data["results"]}

    def test_appears_in_map_search(self, auth_client, nominatim_reverse):
        client, _ = auth_client
        res = self._create(client, latitude="-32.415620", longitude="-63.240000")
        mapa = client.get("/api/reports/map/?search=Rivadavia")
        assert res.data["id"] in {m["id"] for m in mapa.data["results"]}

    def test_explicit_address_is_respected(self, auth_client, nominatim_reverse):
        """Si el usuario escribió la dirección, no la pisamos con la del GPS."""
        client, _ = auth_client
        res = self._create(
            client,
            latitude="-32.415620",
            longitude="-63.240000",
            address="Mi dirección a mano",
        )
        assert Report.objects.get(id=res.data["id"]).address == "Mi dirección a mano"
        assert nominatim_reverse == []

    def test_failure_does_not_block_creation(self, auth_client, monkeypatch):
        """La geocodificación es best-effort: nunca debe romper el alta."""
        import requests

        def boom(*args, **kwargs):
            raise requests.RequestException("sin red")

        monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", boom)
        cache.clear()
        client, _ = auth_client
        res = self._create(client, latitude="-32.415620", longitude="-63.240000")
        assert res.status_code == 201
        assert Report.objects.get(id=res.data["id"]).address == ""


@pytest.mark.django_db
class TestKeywordSearch:
    """US-020: la búsqueda libre debe encontrar por palabra de la descripción."""

    def test_finds_by_keyword_in_description(self, auth_client):
        from urbancheck.reports.tests.factories import ReportFactory

        client, _ = auth_client
        robo = ReportFactory.create(description="Hubo un robo en la esquina")
        ReportFactory.create(description="Bache profundo")

        res = client.get("/api/reports/?search=robo")
        assert {r["id"] for r in res.data["results"]} == {robo.id}

    def test_keyword_search_works_on_map(self, auth_client):
        from urbancheck.reports.tests.factories import ReportFactory

        client, _ = auth_client
        robo = ReportFactory.create(description="Denuncia por robo reiterado")
        ReportFactory.create(description="Semáforo apagado")

        res = client.get("/api/reports/map/?search=robo")
        assert {m["id"] for m in res.data["results"]} == {robo.id}
