"""N-02: el login del admin de Django con límite de intentos.

Es la misma política que el login de la API (``login_failed`` de allauth): 5
intentos fallidos por cuenta en 15 minutos y 10 por minuto por IP. Va aparte
porque ``HEADLESS_ONLY`` (N-16) apagó las vistas HTML de allauth de las que
dependía ``DJANGO_ADMIN_FORCE_ALLAUTH``.
"""

from __future__ import annotations

import logging

import pytest
from django.conf import settings
from django.test import Client

from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105
HTTP_OK = 200
HTTP_FOUND = 302
HTTP_TOO_MANY = 429


def login_url() -> str:
    return f"/{settings.ADMIN_URL}login/"


def attempt(client: Client, email: str, password: str, ip: str = "203.0.113.7"):
    return client.post(
        login_url(),
        {"username": email, "password": password, "next": f"/{settings.ADMIN_URL}"},
        REMOTE_ADDR=ip,
    )


@pytest.fixture
def staff():
    user = UserFactory.create(email="staff@example.com", is_staff=True)
    user.set_password(PASSWORD)
    user.save()
    return user


def test_the_sixth_failed_attempt_on_an_account_answers_429(staff, caplog):
    caplog.set_level(logging.INFO, logger="security")
    client = Client()
    for _ in range(5):
        assert attempt(client, staff.email, "incorrecta").status_code == HTTP_OK

    response = attempt(client, staff.email, "incorrecta")

    assert response.status_code == HTTP_TOO_MANY
    events = [
        record.security
        for record in caplog.records
        if record.name == "security" and hasattr(record, "security")
    ]
    assert any(event["event"] == "login_locked" for event in events)
    # La huella de la cuenta, nunca lo que se escribió.
    assert staff.email not in caplog.text
    assert "incorrecta" not in caplog.text


def test_a_locked_account_is_locked_even_with_the_right_password(staff):
    client = Client()
    for _ in range(5):
        attempt(client, staff.email, "incorrecta")

    assert attempt(client, staff.email, PASSWORD).status_code == HTTP_TOO_MANY


def test_the_ip_is_limited_across_accounts(staff):
    client = Client()
    for number in range(10):
        attempt(client, f"cuenta{number}@example.com", "incorrecta")

    assert attempt(client, staff.email, PASSWORD).status_code == HTTP_TOO_MANY
    # Desde otra IP, la cuenta (sin fallos propios) sigue entrando.
    other = attempt(Client(), staff.email, PASSWORD, ip="198.51.100.9")
    assert other.status_code == HTTP_FOUND


def test_a_successful_login_still_works(staff):
    assert attempt(Client(), staff.email, PASSWORD).status_code == HTTP_FOUND
