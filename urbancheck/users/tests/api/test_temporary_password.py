"""US-017 — flujo completo de contraseña temporal."""

from __future__ import annotations

import json

import pytest
from django.test import Client

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory

LOGIN_URL = "/_allauth/app/v1/auth/login"
CHANGE_PASSWORD_URL = "/_allauth/app/v1/account/password/change"

TEMPORARY_PASSWORD = "Xk7#mP9@qLz2!"
NEW_PASSWORD = "Qw8$rTy4&nBv1?"

pytestmark = pytest.mark.django_db


def json_post(client: Client, url: str, data: dict, token: str | None = None):
    headers = {"HTTP_X_SESSION_TOKEN": token} if token else {}
    return client.post(
        url,
        json.dumps(data),
        content_type="application/json",
        **headers,
    )


@pytest.fixture
def agent() -> User:
    agent = MunicipalAgentFactory.create(
        email="agente@muni.gob.ar",
        municipality=MunicipalityFactory.create(city="Villa María", province="Córdoba"),
        must_change_password=True,
    )
    agent.set_password(TEMPORARY_PASSWORD)
    agent.save()
    return agent


class TestLoginPayload:
    def test_login_carries_role_municipality_and_flag(self, client, agent):
        """El panel decide el flujo sin una segunda llamada."""
        response = json_post(
            client,
            LOGIN_URL,
            {"email": agent.email, "password": TEMPORARY_PASSWORD},
        )

        assert response.status_code == 200
        user_data = response.json()["data"]["user"]
        assert user_data["role"] == User.Role.AGENTE_MUNICIPAL
        assert user_data["must_change_password"] is True
        assert user_data["municipality"]["city"] == "Villa María"

    def test_municipality_travels_as_null_for_a_citizen(self, client):
        from urbancheck.users.tests.factories import UserFactory

        citizen = UserFactory.create(email="vecino@test.com")
        citizen.set_password(TEMPORARY_PASSWORD)
        citizen.save()

        response = json_post(
            client,
            LOGIN_URL,
            {"email": citizen.email, "password": TEMPORARY_PASSWORD},
        )

        user_data = response.json()["data"]["user"]
        # Que llegue en null es información, no ausencia de dato.
        assert user_data["municipality"] is None
        assert user_data["must_change_password"] is False


class TestPasswordChange:
    def test_changing_the_password_clears_the_flag(self, client, agent):
        login = json_post(
            client,
            LOGIN_URL,
            {"email": agent.email, "password": TEMPORARY_PASSWORD},
        )
        token = login.json()["meta"]["session_token"]

        response = json_post(
            client,
            CHANGE_PASSWORD_URL,
            {"current_password": TEMPORARY_PASSWORD, "new_password": NEW_PASSWORD},
            token=token,
        )

        assert response.status_code == 200
        agent.refresh_from_db()
        assert agent.must_change_password is False
        assert agent.check_password(NEW_PASSWORD)

    def test_wrong_current_password_keeps_the_flag(self, client, agent):
        login = json_post(
            client,
            LOGIN_URL,
            {"email": agent.email, "password": TEMPORARY_PASSWORD},
        )
        token = login.json()["meta"]["session_token"]

        response = json_post(
            client,
            CHANGE_PASSWORD_URL,
            {"current_password": "incorrecta", "new_password": NEW_PASSWORD},
            token=token,
        )

        assert response.status_code == 400
        agent.refresh_from_db()
        assert agent.must_change_password is True

    def test_flag_is_untouched_for_a_user_that_never_had_it(self, client):
        from urbancheck.users.tests.factories import UserFactory

        citizen = UserFactory.create(email="vecino2@test.com")
        citizen.set_password(TEMPORARY_PASSWORD)
        citizen.save()
        login = json_post(
            client,
            LOGIN_URL,
            {"email": citizen.email, "password": TEMPORARY_PASSWORD},
        )
        token = login.json()["meta"]["session_token"]

        json_post(
            client,
            CHANGE_PASSWORD_URL,
            {"current_password": TEMPORARY_PASSWORD, "new_password": NEW_PASSWORD},
            token=token,
        )

        citizen.refresh_from_db()
        assert citizen.must_change_password is False
