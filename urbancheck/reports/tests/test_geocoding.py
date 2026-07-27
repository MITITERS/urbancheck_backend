from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.reports import geocoding
from urbancheck.reports.models import Report
from urbancheck.users.tests.factories import UserFactory


def make_image_file(name="test.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color=(100, 100, 100)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


@pytest.fixture
def auth_client(db):
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def _fake_nominatim(monkeypatch, payload):
    """Parchea requests.get para devolver ``payload`` como respuesta de Nominatim."""
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    monkeypatch.setattr(geocoding.requests, "get", MagicMock(return_value=response))


NOMINATIM_HIT = [
    {"display_name": "Av. Corrientes 1234, CABA, Argentina", "lat": "-34.6037", "lon": "-58.3816"},
]


class TestSearchAddresses:
    def test_short_query_returns_empty_without_network(self, monkeypatch):
        called = MagicMock()
        monkeypatch.setattr(geocoding.requests, "get", called)
        assert geocoding.search_addresses("ab") == []
        called.assert_not_called()

    def test_parses_results(self, monkeypatch):
        _fake_nominatim(monkeypatch, NOMINATIM_HIT)
        results = geocoding.search_addresses("Corrientes 1234")
        assert results == [
            {
                "display_name": "Av. Corrientes 1234, CABA, Argentina",
                "latitude": -34.6037,
                "longitude": -58.3816,
            }
        ]

    def test_network_error_returns_empty(self, monkeypatch):
        boom = MagicMock(side_effect=geocoding.requests.RequestException("down"))
        monkeypatch.setattr(geocoding.requests, "get", boom)
        assert geocoding.search_addresses("Corrientes 1234") == []

    def test_caches_second_call(self, monkeypatch):
        getter = MagicMock()
        getter.return_value.json.return_value = NOMINATIM_HIT
        getter.return_value.raise_for_status.return_value = None
        monkeypatch.setattr(geocoding.requests, "get", getter)
        geocoding.search_addresses("Corrientes 4321")
        geocoding.search_addresses("Corrientes 4321")
        assert getter.call_count == 1


@pytest.mark.django_db
class TestGeocodeEndpoint:
    def test_returns_suggestions(self, auth_client, monkeypatch):
        client, _ = auth_client
        _fake_nominatim(monkeypatch, NOMINATIM_HIT)
        res = client.get("/api/reports/geocode/?q=Corrientes 1234")
        assert res.status_code == 200
        assert res.data["results"][0]["latitude"] == -34.6037

    def test_requires_auth(self, db):
        res = APIClient().get("/api/reports/geocode/?q=Corrientes 1234")
        assert res.status_code in (401, 403)


@pytest.mark.django_db
class TestCreateGeocodeFallback:
    def test_address_without_coords_is_geocoded(self, auth_client, monkeypatch):
        client, _ = auth_client
        _fake_nominatim(monkeypatch, NOMINATIM_HIT)
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Bache profundo",
                "category": "bache",
                "address": "Av. Corrientes 1234",
            },
            format="multipart",
        )
        assert res.status_code == 201
        report = Report.objects.get(id=res.data["id"])
        assert float(report.latitude) == pytest.approx(-34.6037)
        assert float(report.longitude) == pytest.approx(-58.3816)

    def test_explicit_coords_are_not_overwritten(self, auth_client, monkeypatch):
        client, _ = auth_client
        getter = MagicMock()
        monkeypatch.setattr(geocoding.requests, "get", getter)
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Con GPS",
                "category": "bache",
                "latitude": "-34.9",
                "longitude": "-58.1",
                "address": "Av. Corrientes 1234",
            },
            format="multipart",
        )
        assert res.status_code == 201
        report = Report.objects.get(id=res.data["id"])
        assert float(report.latitude) == pytest.approx(-34.9)
        getter.assert_not_called()

    def test_geocode_failure_still_creates_report(self, auth_client):
        # El fixture autouse _no_geocoding_network hace fallar la geocodificación.
        client, _ = auth_client
        res = client.post(
            "/api/reports/",
            data={
                "photo": make_image_file(),
                "description": "Sin resolver",
                "category": "bache",
                "address": "Dirección inexistente xyz",
            },
            format="multipart",
        )
        assert res.status_code == 201
        report = Report.objects.get(id=res.data["id"])
        assert report.latitude is None
        assert report.longitude is None
