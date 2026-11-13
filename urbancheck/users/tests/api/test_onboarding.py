"""US-051 — tutorial de bienvenida: la marca que decide si la app lo muestra.

La marca vive en la cuenta, no en el dispositivo: es lo que hace que el
tutorial no reaparezca al reinstalar la app o al cambiar de teléfono.
"""

from __future__ import annotations

import importlib
import json
from datetime import timedelta
from http import HTTPStatus

import pytest
from django.apps import apps as django_apps
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.users.adapters import HeadlessAdapter
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

ONBOARDING_URL = "/api/users/me/onboarding/"
ME_URL = "/api/users/me/"
SIGNUP_URL = "/_allauth/app/v1/auth/signup"
PASSWORD = "Qw8$rTy4&nBv1?"  # noqa: S105


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestNewCitizen:
    def test_a_new_citizen_has_no_mark(self):
        """CP-051-01 (US-051 E1). Recién creado, el tutorial está por ver."""
        citizen = UserFactory.create()

        assert citizen.onboarding_completed_at is None

    def test_a_citizen_who_signs_up_gets_a_null_mark_in_the_response(self, client):
        """CP-051-02 (US-051 E1). El registro devuelve la marca sin llamada extra."""
        response = client.post(
            SIGNUP_URL,
            json.dumps(
                {"email": "vecina@example.com", "password": PASSWORD, "name": "Vecina"},
            ),
            content_type="application/json",
        )

        assert response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}
        user = User.objects.get(email="vecina@example.com")
        assert user.onboarding_completed_at is None
        assert response.json()["data"]["user"]["onboarding_completed_at"] is None

    def test_the_mark_travels_in_the_login_payload_even_when_null(self):
        """CP-051-03 (US-051 E1). El adapter base descarta los nulos; este no."""
        citizen = UserFactory.create()

        data = HeadlessAdapter().serialize_user(citizen)

        assert "onboarding_completed_at" in data
        assert data["onboarding_completed_at"] is None

    def test_the_mark_travels_in_the_profile(self):
        """CP-051-04 (US-051 E1)."""
        citizen = UserFactory.create()

        response = client_for(citizen).get(ME_URL)

        assert response.status_code == HTTPStatus.OK
        assert response.data["onboarding_completed_at"] is None

    def test_the_mark_cannot_be_written_through_the_profile(self):
        """CP-051-05. El PATCH del perfil no sirve para marcarlo ni para borrarlo."""
        seen_at = timezone.now() - timedelta(days=3)
        citizen = UserFactory.create(onboarding_completed_at=seen_at)

        client_for(citizen).patch(
            ME_URL,
            {"onboarding_completed_at": None},
            format="json",
        )

        citizen.refresh_from_db()
        assert citizen.onboarding_completed_at == seen_at


class TestMarkingAsSeen:
    def test_finishing_or_skipping_marks_the_account(self):
        """CP-051-06 (US-051 E3, E4). Terminar y omitir llaman al mismo endpoint."""
        citizen = UserFactory.create()

        response = client_for(citizen).post(ONBOARDING_URL)

        assert response.status_code == HTTPStatus.OK
        citizen.refresh_from_db()
        assert citizen.onboarding_completed_at is not None
        assert response.data["onboarding_completed_at"] is not None

    def test_a_second_call_does_not_overwrite_the_original_date(self):
        """CP-051-07 (US-051 E5, E10). El reintento no pisa la fecha."""
        seen_at = timezone.now() - timedelta(days=10)
        citizen = UserFactory.create(onboarding_completed_at=seen_at)

        response = client_for(citizen).post(ONBOARDING_URL)

        assert response.status_code == HTTPStatus.OK
        citizen.refresh_from_db()
        assert citizen.onboarding_completed_at == seen_at

    def test_it_requires_a_session(self):
        """CP-051-08."""
        response = APIClient().post(ONBOARDING_URL)

        assert response.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}

    @pytest.mark.parametrize(
        "factory",
        [
            ValidatorFactory,
            OperatorFactory,
            MunicipalAgentFactory,
            PlatformAdminFactory,
        ],
        ids=["validador", "operario", "agente", "admin"],
    )
    def test_other_roles_are_rejected(self, factory):
        """CP-051-09 (US-051 E8). El tutorial es solo para el vecino."""
        worker = factory.create()

        response = client_for(worker).post(ONBOARDING_URL)

        assert response.status_code == HTTPStatus.FORBIDDEN
        worker.refresh_from_db()
        assert worker.onboarding_completed_at is None


class TestExistingAccountsMigration:
    """La migración marca a todas las cuentas que ya existían (escenario 9)."""

    @staticmethod
    def _mark_existing_users():
        module = importlib.import_module(
            "urbancheck.users.migrations.0010_user_onboarding_completed_at",
        )
        return module.mark_existing_users

    def test_existing_accounts_are_marked_as_seen(self):
        """CP-051-10 (US-051 E9)."""
        citizen = UserFactory.create()
        agent = MunicipalAgentFactory.create()

        self._mark_existing_users()(django_apps, None)

        citizen.refresh_from_db()
        agent.refresh_from_db()
        assert citizen.onboarding_completed_at is not None
        assert agent.onboarding_completed_at is not None

    def test_it_keeps_a_date_that_was_already_there(self):
        """CP-051-11 (US-051 E9). Volver a correrla no reescribe nada."""
        seen_at = timezone.now() - timedelta(days=30)
        citizen = UserFactory.create(onboarding_completed_at=seen_at)

        self._mark_existing_users()(django_apps, None)

        citizen.refresh_from_db()
        assert citizen.onboarding_completed_at == seen_at
