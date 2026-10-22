"""Política de contenido de Django en el admin y en Swagger (C-05).

Django 6.0 trae ``ContentSecurityPolicyMiddleware`` y ``SECURE_CSP``. Acá se
aplica solo a las dos pantallas HTML de administración; la API responde JSON y
las páginas públicas (la vista previa de un reporte compartido) tienen su
propia redirección inline, que esta política rompería.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client

from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

HEADER = "Content-Security-Policy"


def directives(response) -> dict[str, list[str]]:
    policy = response.headers[HEADER]
    return {
        name: values
        for name, *values in (part.split() for part in policy.split(";") if part)
    }


@pytest.fixture
def staff_client() -> Client:
    client = Client()
    client.force_login(UserFactory.create(is_staff=True, is_superuser=True))
    return client


class TestTheAdminHasAPolicy:
    def test_the_login_page(self, client):
        response = client.get(f"/{settings.ADMIN_URL}login/")

        policy = directives(response)
        assert policy["default-src"] == ["'self'"]
        assert policy["frame-ancestors"] == ["'none'"]
        assert "'unsafe-inline'" not in policy["script-src"]
        assert "'unsafe-eval'" not in policy["script-src"]

    def test_a_changelist(self, staff_client):
        response = staff_client.get(f"/{settings.ADMIN_URL}users/user/")

        assert response.status_code == 200  # noqa: PLR2004
        assert HEADER in response.headers


class TestSwaggerHasAPolicy:
    def test_the_docs_page_carries_it(self, staff_client):
        response = staff_client.get("/api/docs/")

        assert response.status_code == 200  # noqa: PLR2004
        policy = directives(response)
        assert "'unsafe-inline'" not in policy["script-src"]

    def test_the_page_has_no_inline_script(self, staff_client):
        """Swagger arranca desde un script aparte: la política no admite inline."""
        html = staff_client.get("/api/docs/").content.decode()

        assert "<script>" not in html
        assert "?script" in html


class TestTheRestIsLeftAlone:
    def test_the_api(self, staff_client):
        response = staff_client.get("/api/reports/")

        assert HEADER not in response.headers

    def test_the_shared_report_preview(self, client):
        report = ReportFactory.create()

        response = client.get(f"/r/{report.share_token}")

        assert HEADER not in response.headers
