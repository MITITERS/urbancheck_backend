"""N-13: Swagger UI se sirve desde el servidor, no desde un CDN sin versión.

Con ``drf-spectacular-sidecar`` los archivos de Swagger UI vienen en un paquete
de Python con versión fijada en ``uv.lock`` y se sirven como estáticos propios.
La política de contenido (C-05) deja de admitir el CDN.
"""

from __future__ import annotations

import re

import pytest
from django.conf import settings
from django.test import Client

from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client() -> Client:
    client = Client()
    client.force_login(UserFactory.create(is_staff=True, is_superuser=True))
    return client


def test_swagger_assets_are_served_from_the_server(staff_client):
    html = staff_client.get("/api/docs/").content.decode()
    script = staff_client.get("/api/docs/?script").content.decode()

    assert "cdn.jsdelivr.net" not in html + script
    assets = re.findall(r'(?:src|href)="([^"]+swagger-ui[^"]+)"', html)
    assert assets
    assert all(asset.startswith(settings.STATIC_URL) for asset in assets)


def test_the_policy_allows_no_external_origin(staff_client):
    policy = staff_client.get("/api/docs/").headers["Content-Security-Policy"]

    assert "https://" not in policy
    assert "script-src 'self'" in policy
