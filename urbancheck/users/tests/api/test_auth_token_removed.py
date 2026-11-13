"""N-01: la ruta ``/api/auth-token/`` y ``TokenAuthentication`` de la plantilla.

Emitían un token sin vencimiento ni revocación, desde un login sin límite de
intentos. Ningún cliente los usa: el panel y la app se autentican con la
sesión headless de allauth (``X-Session-Token``).
"""

from __future__ import annotations

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105


def test_the_auth_token_route_does_not_exist():
    user = UserFactory.create(email="vecina@example.com")
    user.set_password(PASSWORD)
    user.save()

    response = APIClient().post(
        "/api/auth-token/",
        {"username": user.email, "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 404  # noqa: PLR2004


def test_a_drf_token_header_does_not_authenticate():
    user = UserFactory.create()
    if apps.is_installed("rest_framework.authtoken"):
        # Con la app instalada, un token real: así el test prueba que la
        # cabecera deja de autenticar, y no solo que la clave es inválida.
        from rest_framework.authtoken.models import Token  # noqa: PLC0415

        key = Token.objects.create(user=user).key
    else:
        key = "0" * 40

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    response = client.get("/api/users/me/")

    # Sin credenciales válidas, la API responde 403: la primera clase de
    # autenticación (la de allauth) no define ``authenticate_header``.
    assert response.status_code == 403  # noqa: PLR2004

