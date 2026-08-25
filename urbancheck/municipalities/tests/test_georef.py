"""Catálogo de provincias y localidades (Georef).

Ningún test sale a la red: el conftest la bloquea y cada caso decide qué
responde el servicio.
"""

import pytest
import requests
from django.core.cache import cache
from rest_framework.test import APIClient

from urbancheck.municipalities import georef
from urbancheck.users.tests.factories import PlatformAdminFactory

PROVINCES_URL = "/api/geo/provinces/"
CORDOBA_ID = "14"

pytestmark = pytest.mark.django_db

PROVINCES_PAYLOAD = {
    "provincias": [
        {"id": "14", "nombre": "Córdoba"},
        {"id": "06", "nombre": "Buenos Aires"},
    ],
}

LOCALITIES_PAYLOAD = {
    "localidades": [
        {
            "id": "14182060",
            "nombre": "Bell Ville",
            "centroide": {"lat": -32.6303, "lon": -62.6888},
        },
        {
            "id": "14098230",
            "nombre": "Alta Gracia",
            "centroide": {"lat": -31.6539, "lon": -64.4281},
        },
        # Sin centroide: no sirve para ubicar el área de cobertura.
        {"id": "14000000", "nombre": "Sin centro", "centroide": None},
    ],
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(PlatformAdminFactory.create())
    return client


@pytest.fixture
def georef_responds(monkeypatch):
    """Hace que Georef conteste lo que el test indique, contando llamadas."""
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params))
        payload = (
            PROVINCES_PAYLOAD if url.endswith("provincias") else LOCALITIES_PAYLOAD
        )
        return FakeResponse(payload)

    monkeypatch.setattr("urbancheck.municipalities.georef.requests.get", fake_get)
    return calls


class TestProvinces:
    def test_it_lists_the_provinces_alphabetically(self, admin_client, georef_responds):
        response = admin_client.get(PROVINCES_URL)

        assert response.status_code == 200
        assert [p["name"] for p in response.data["results"]] == [
            "Buenos Aires",
            "Córdoba",
        ]

    def test_the_result_is_cached(self, admin_client, georef_responds):
        admin_client.get(PROVINCES_URL)
        admin_client.get(PROVINCES_URL)

        # La división política no cambia: una sola salida a la red.
        assert len(georef_responds) == 1

    def test_a_georef_outage_falls_back_to_the_static_list(self, admin_client):
        """El formulario no puede quedar inutilizable por un corte del servicio."""
        response = admin_client.get(PROVINCES_URL)

        assert response.status_code == 200
        assert len(response.data["results"]) == len(georef.FALLBACK_PROVINCES)
        assert any(p["name"] == "Córdoba" for p in response.data["results"])

    def test_the_fallback_is_not_cached(self, admin_client, monkeypatch):
        admin_client.get(PROVINCES_URL)

        assert cache.get("georef:provinces") is None


class TestLocalities:
    def test_it_lists_the_localities_with_their_centre(
        self,
        admin_client,
        georef_responds,
    ):
        response = admin_client.get(f"{PROVINCES_URL}{CORDOBA_ID}/localities/")

        assert response.status_code == 200
        bell_ville = response.data["results"][1]
        assert bell_ville["name"] == "Bell Ville"
        assert bell_ville["latitude"] == pytest.approx(-32.6303)
        assert bell_ville["longitude"] == pytest.approx(-62.6888)

    def test_localities_without_a_centre_are_left_out(
        self,
        admin_client,
        georef_responds,
    ):
        """Sin centroide no sirven para ubicar el área de cobertura."""
        response = admin_client.get(f"{PROVINCES_URL}{CORDOBA_ID}/localities/")

        assert "Sin centro" not in {r["name"] for r in response.data["results"]}

    def test_they_come_sorted_by_name(self, admin_client, georef_responds):
        response = admin_client.get(f"{PROVINCES_URL}{CORDOBA_ID}/localities/")

        names = [r["name"] for r in response.data["results"]]
        assert names == sorted(names)

    def test_the_province_is_asked_for_explicitly(self, admin_client, georef_responds):
        admin_client.get(f"{PROVINCES_URL}{CORDOBA_ID}/localities/")

        _, params = georef_responds[0]
        assert params["provincia"] == CORDOBA_ID

    def test_an_outage_returns_an_empty_list_instead_of_failing(self, admin_client):
        response = admin_client.get(f"{PROVINCES_URL}{CORDOBA_ID}/localities/")

        assert response.status_code == 200
        assert response.data["results"] == []

    def test_an_unreadable_response_is_survived(self, admin_client, monkeypatch):
        class Broken(FakeResponse):
            def json(self):
                msg = "no es json"
                raise ValueError(msg)

        monkeypatch.setattr(
            "urbancheck.municipalities.georef.requests.get",
            lambda *a, **k: Broken(None),
        )

        response = admin_client.get(f"{PROVINCES_URL}{CORDOBA_ID}/localities/")

        assert response.status_code == 200
        assert response.data["results"] == []


class TestPermissions:
    def test_anonymous_is_denied(self):
        assert APIClient().get(PROVINCES_URL).status_code == 403


def test_a_network_error_never_escapes(monkeypatch):
    """La regla del módulo: Georef nunca rompe el flujo del panel."""

    def explode(*args, **kwargs):
        raise requests.RequestException

    monkeypatch.setattr("urbancheck.municipalities.georef.requests.get", explode)

    assert georef.list_localities("14") == []
    assert georef.list_provinces() == georef.FALLBACK_PROVINCES
