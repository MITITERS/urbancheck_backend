"""N-06: la página pública no expone el id ni la ubicación exacta.

El id es correlativo: muestra el volumen de reportes y sirve para recorrerlos.
Las coordenadas se redondean (3 decimales, unos 100 m): alcanzan para ubicar
el problema en el mapa sin marcar la puerta de quien lo reportó.

La app, con sesión, sigue abriendo el detalle desde un enlace: resuelve el
token con ``/api/reports/shared/<token>/``, que pide sesión.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def public(report):
    return APIClient().get(f"/api/public/reports/{report.share_token}/")


def resolve(report, user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client.get(f"/api/reports/shared/{report.share_token}/")


@pytest.fixture
def report():
    return ReportFactory.create(
        latitude=Decimal("-32.4107531"),
        longitude=Decimal("-63.2405129"),
    )


def test_the_public_report_has_no_id(report):
    data = public(report).json()

    assert "id" not in data
    assert data["number"] == report.number


def test_the_coordinates_are_rounded_to_three_decimals(report):
    data = public(report).json()

    assert data["latitude"] == "-32.411"
    assert data["longitude"] == "-63.241"


def test_the_precision_is_configurable(report, settings):
    settings.PUBLIC_COORDINATE_DECIMALS = 2

    data = public(report).json()

    assert data["latitude"] == "-32.41"
    assert data["longitude"] == "-63.24"


def test_a_report_without_location_stays_without_it():
    report = ReportFactory.create(latitude=None, longitude=None)

    data = public(report).json()

    assert data["latitude"] is None
    assert data["longitude"] is None


def test_with_a_session_the_token_resolves_to_the_id(report):
    response = resolve(report, UserFactory.create())

    assert response.status_code == 200  # noqa: PLR2004
    assert response.json() == {"id": report.pk}


def test_without_a_session_it_does_not(report):
    assert resolve(report).status_code == 403  # noqa: PLR2004


def test_a_report_that_is_not_public_does_not_resolve():
    report = ReportFactory.create(status=Report.Status.CANCELADO)

    assert resolve(report, UserFactory.create()).status_code == 404  # noqa: PLR2004


def test_the_preview_title_does_not_fall_back_to_the_id(report):
    Report.objects.filter(pk=report.pk).update(number=None)

    html = APIClient().get(f"/r/{report.share_token}").content.decode()

    assert f"#{report.pk}" not in html
