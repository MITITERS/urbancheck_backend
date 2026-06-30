from __future__ import annotations

import pytest
from django.core import mail
from django.test import Client

from urbancheck.users.tests.factories import UserFactory


SIGNUP_URL = "/_allauth/app/v1/auth/signup"
LOGIN_URL = "/_allauth/app/v1/auth/login"
SESSION_URL = "/_allauth/app/v1/auth/session"
PASSWORD_REQUEST_URL = "/_allauth/app/v1/auth/password/request"

STRONG_PASSWORD = "Xk7#mP9@qLz2!"


def json_post(client: Client, url: str, data: dict) -> object:
    import json

    return client.post(url, json.dumps(data), content_type="application/json")


def json_delete(client: Client, url: str, token: str | None = None) -> object:
    headers = {}
    if token:
        headers["HTTP_X_SESSION_TOKEN"] = token
    return client.delete(url, content_type="application/json", **headers)


def json_get(client: Client, url: str, token: str | None = None) -> object:
    headers = {}
    if token:
        headers["HTTP_X_SESSION_TOKEN"] = token
    return client.get(url, content_type="application/json", **headers)


@pytest.fixture
def client(db):
    return Client()


@pytest.mark.django_db
class TestSignup:
    def test_signup_returns_session_token(self, client):
        res = json_post(
            client,
            SIGNUP_URL,
            {
                "email": "nuevo@example.com",
                "password": STRONG_PASSWORD,
                "name": "Juan Pérez",
            },
        )
        assert res.status_code in (200, 201)
        data = res.json()
        assert "session_token" in data["meta"]

    def test_signup_sets_role_ciudadano(self, client):
        from urbancheck.users.models import User

        json_post(
            client,
            SIGNUP_URL,
            {
                "email": "ciudadano@example.com",
                "password": STRONG_PASSWORD,
                "name": "Ciudadano Test",
            },
        )
        user = User.objects.get(email="ciudadano@example.com")
        assert user.role == "ciudadano"
        assert user.name == "Ciudadano Test"

    def test_signup_sends_email(self, client):
        json_post(
            client,
            SIGNUP_URL,
            {
                "email": "mail@example.com",
                "password": STRONG_PASSWORD,
                "name": "Test User",
            },
        )
        assert len(mail.outbox) >= 1

    def test_signup_duplicate_email_returns_error(self, client):
        UserFactory.create(email="dup@example.com")
        res = json_post(
            client,
            SIGNUP_URL,
            {
                "email": "dup@example.com",
                "password": STRONG_PASSWORD,
                "name": "Dup User",
            },
        )
        assert res.status_code in (400, 409)

    def test_signup_short_password_returns_error(self, client):
        res = json_post(
            client,
            SIGNUP_URL,
            {
                "email": "short@example.com",
                "password": "abc",
                "name": "Short Pass",
            },
        )
        assert res.status_code in (400, 409)


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_session_token(self, client):
        user = UserFactory.create(email="login@example.com")
        user.set_password(STRONG_PASSWORD)
        user.save()
        res = json_post(
            client,
            LOGIN_URL,
            {"email": "login@example.com", "password": STRONG_PASSWORD},
        )
        assert res.status_code == 200
        data = res.json()
        assert "session_token" in data["meta"]

    def test_login_bad_credentials_returns_generic_error(self, client):
        res = json_post(
            client,
            LOGIN_URL,
            {"email": "nobody@example.com", "password": "wrongpass"},
        )
        assert res.status_code in (400, 401)
        body = res.content.decode()
        assert "session_token" not in body


@pytest.mark.django_db
class TestLogout:
    def test_logout_invalidates_session(self, client):
        user = UserFactory.create(email="logout@example.com")
        user.set_password(STRONG_PASSWORD)
        user.save()
        login_res = json_post(
            client,
            LOGIN_URL,
            {"email": "logout@example.com", "password": STRONG_PASSWORD},
        )
        token = login_res.json()["meta"]["session_token"]

        logout_res = json_delete(client, SESSION_URL, token=token)
        assert logout_res.status_code in (204, 401)

        # Token should no longer grant access to protected DRF endpoint
        import json as json_lib
        from django.test import Client as DjClient

        c2 = DjClient()
        me_res = c2.get(
            "/api/users/me/",
            HTTP_X_SESSION_TOKEN=token,
            content_type="application/json",
        )
        assert me_res.status_code in (401, 403, 410)


@pytest.mark.django_db
class TestPasswordReset:
    def test_reset_request_sends_email(self, client):
        user = UserFactory.create(email="reset@example.com")
        res = json_post(
            client,
            PASSWORD_REQUEST_URL,
            {"email": user.email},
        )
        assert res.status_code in (200, 201)
        assert len(mail.outbox) >= 1
