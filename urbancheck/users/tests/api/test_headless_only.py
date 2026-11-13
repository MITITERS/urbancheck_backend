"""N-16: allauth solo como API (``HEADLESS_ONLY``).

Las páginas HTML de ``/accounts/`` eran una superficie que ningún cliente
usaba. Los enlaces de los correos siguen llegando a destinos que existen: la
recuperación, al Universal Link ``/reset-password`` (que abre la app o, sin
ella, la página pública del panel); la confirmación, a la página del panel.
"""

from __future__ import annotations

import json
import re
from http import HTTPStatus

import pytest
from django.core import mail
from django.test import Client

from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

SIGNUP_URL = "/_allauth/app/v1/auth/signup"
PASSWORD_REQUEST_URL = "/_allauth/app/v1/auth/password/request"  # noqa: S105
PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105
RECOVERY_LINK = "https://urbancheck.com.ar/reset-password?key={key}"
PANEL_RESET_PAGE = "https://panel.urbancheck.com.ar/restablecer-contrasena?key={key}"


def post_json(client: Client, url: str, data: dict):
    return client.post(url, json.dumps(data), content_type="application/json")


@pytest.mark.parametrize(
    "path",
    [
        "/accounts/login/",
        "/accounts/signup/",
        "/accounts/logout/",
        "/accounts/password/reset/",
        "/accounts/password/reset/key/1-abc/",
        "/accounts/confirm-email/abc/",
        "/accounts/email/",
    ],
)
def test_the_allauth_html_pages_no_longer_answer(path):
    assert Client().get(path).status_code == HTTPStatus.NOT_FOUND


def test_the_recovery_email_still_carries_the_reset_password_link(settings):
    settings.ACCOUNT_RESET_PASSWORD_URL = RECOVERY_LINK
    settings.HEADLESS_FRONTEND_URLS = {
        **settings.HEADLESS_FRONTEND_URLS,
        "account_reset_password_from_key": settings.ACCOUNT_RESET_PASSWORD_URL,
    }
    UserFactory.create(email="vecina@example.com")

    response = post_json(
        Client(),
        PASSWORD_REQUEST_URL,
        {"email": "vecina@example.com"},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(mail.outbox) == 1
    link = re.search(r"https://\S+", mail.outbox[0].body).group(0)
    assert re.fullmatch(r"https://urbancheck\.com\.ar/reset-password\?key=\S+", link)


def test_the_confirmation_email_links_to_the_panel_page(settings):
    page = settings.EMAIL_CONFIRMATION_URL.split("{key}")[0]

    response = post_json(
        Client(),
        SIGNUP_URL,
        {"email": "nueva@example.com", "password": PASSWORD, "name": "Nueva"},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(mail.outbox) == 1
    assert page.endswith("/confirmar-correo?key=")
    assert page in mail.outbox[0].body


def test_without_the_app_the_reset_link_lands_on_the_panel_page(settings):
    settings.PASSWORD_RESET_PAGE_URL = PANEL_RESET_PAGE

    response = Client().get("/reset-password", {"key": "1-abc&x=y"})

    assert response.status_code == HTTPStatus.FOUND
    assert response["Location"] == (
        "https://panel.urbancheck.com.ar/restablecer-contrasena?key=1-abc%26x%3Dy"
    )
