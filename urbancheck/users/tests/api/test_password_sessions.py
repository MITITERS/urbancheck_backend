"""N-04: cambiar o restablecer la contraseña cierra las otras sesiones.

Sin esto, un token robado (``X-Session-Token``) sobrevivía al cambio de
contraseña hasta vencer, a los 14 días. Al cambiarla se conserva la sesión
desde la que se cambió; al restablecerla, que se hace sin sesión, se cierran
todas.
"""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from urllib.parse import unquote

import pytest
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client

from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/_allauth/app/v1/auth/login"
SESSION_URL = "/_allauth/app/v1/auth/session"
CHANGE_URL = "/_allauth/app/v1/account/password/change"
REQUEST_URL = "/_allauth/app/v1/auth/password/request"
RESET_URL = "/_allauth/app/v1/auth/password/reset"
PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105
NEW_PASSWORD = "Otra#Clave99x"  # noqa: S105


def post(url: str, data: dict, token: str | None = None):
    headers = {"HTTP_X_SESSION_TOKEN": token} if token else {}
    return Client().post(
        url,
        json.dumps(data),
        content_type="application/json",
        **headers,
    )


def session_status(token: str) -> int:
    return Client().get(SESSION_URL, HTTP_X_SESSION_TOKEN=token).status_code


def assert_closed(token: str) -> None:
    """La sesión ya no existe: allauth responde 410 y la API no la reconoce.

    410 y no 401: es lo que contesta allauth headless cuando el token ya no
    corresponde a ninguna sesión. La app trata los dos igual (cierra la
    sesión); el panel arranca por la API, que responde 403 sin sesión.
    """
    assert session_status(token) == HTTPStatus.GONE
    api = Client().get("/api/users/me/", HTTP_X_SESSION_TOKEN=token)
    assert api.status_code == HTTPStatus.FORBIDDEN


@pytest.fixture
def account():
    user = UserFactory.create(email="vecina@example.com")
    user.set_password(PASSWORD)
    user.save()
    return user


def open_session(email: str) -> str:
    response = post(LOGIN_URL, {"email": email, "password": PASSWORD})
    assert response.status_code == HTTPStatus.OK
    return response.json()["meta"]["session_token"]


def test_changing_the_password_closes_the_other_session(account):
    phone = open_session(account.email)
    stolen = open_session(account.email)

    response = post(
        CHANGE_URL,
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        token=phone,
    )

    assert response.status_code == HTTPStatus.OK
    # allauth rota el token de la sesión desde la que se cambió y devuelve el
    # nuevo. Se mira la base antes de usar los tokens: un pedido con una sesión
    # de hash viejo la borra por su cuenta, y escondería si se cerró o no.
    current = response.json()["meta"]["session_token"]
    assert list(Session.objects.values_list("session_key", flat=True)) == [current]
    assert_closed(stolen)
    assert session_status(current) == HTTPStatus.OK


def test_resetting_the_password_closes_every_session(account):
    phone = open_session(account.email)
    stolen = open_session(account.email)
    other = UserFactory.create(email="otra@example.com")
    other.set_password(PASSWORD)
    other.save()
    bystander = open_session(other.email)

    post(REQUEST_URL, {"email": account.email})
    # El enlace es el Universal Link (``?key=``) o, según el entorno, otra URL
    # con la clave al final.
    key = unquote(re.search(r"key[=/]([^\s/]+)", mail.outbox[-1].body).group(1))
    response = post(RESET_URL, {"key": key, "password": NEW_PASSWORD})
    # Sin sesión, allauth responde 401 cuando el reset sale bien.
    assert response.status_code == HTTPStatus.UNAUTHORIZED

    # Las sesiones de otras cuentas no se tocan.
    assert list(Session.objects.values_list("session_key", flat=True)) == [bystander]
    assert_closed(phone)
    assert_closed(stolen)
    assert session_status(bystander) == HTTPStatus.OK
