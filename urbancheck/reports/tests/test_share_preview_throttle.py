"""N-05: la vista previa ``/r/{token}`` con límite de tasa.

Es pública y arma la tarjeta con una consulta por pedido, igual que el
endpoint de la página pública. Lleva su mismo alcance, ``public_reports``
(120 por hora por IP), y comparte el contador: es el mismo reporte visto por
otra puerta.
"""

from __future__ import annotations

import pytest
from django.test import Client
from rest_framework.test import APIClient

from urbancheck.reports.tests.factories import ReportFactory

pytestmark = pytest.mark.django_db

LIMIT = 120
HTTP_TOO_MANY = 429


def preview(client: Client, token, ip: str = "203.0.113.7"):
    return client.get(f"/r/{token}", REMOTE_ADDR=ip)


def test_the_121st_preview_from_one_ip_answers_429():
    report = ReportFactory.create()
    client = Client()
    for _ in range(LIMIT):
        assert preview(client, report.share_token).status_code != HTTP_TOO_MANY

    response = preview(client, report.share_token)

    assert response.status_code == HTTP_TOO_MANY
    assert int(response["Retry-After"]) > 0


def test_another_ip_keeps_its_own_count():
    report = ReportFactory.create()
    for _ in range(LIMIT + 1):
        preview(Client(), report.share_token)

    response = preview(Client(), report.share_token, ip="198.51.100.9")

    assert response.status_code != HTTP_TOO_MANY


def test_the_preview_and_the_public_endpoint_share_the_count():
    report = ReportFactory.create()
    api = APIClient()
    for _ in range(LIMIT):
        api.get(
            f"/api/public/reports/{report.share_token}/",
            REMOTE_ADDR="203.0.113.7",
        )

    assert preview(Client(), report.share_token).status_code == HTTP_TOO_MANY
