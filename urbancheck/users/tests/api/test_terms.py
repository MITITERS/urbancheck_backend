"""RN-10 (C-23) — aceptación de los términos y condiciones.

El vecino acepta la versión vigente al registrarse; las cuentas que ya
existían la aceptan en su próximo ingreso, y lo mismo pasa cada vez que se
publica una versión nueva. Mientras no haya términos publicados no se exige
nada: el texto lo carga el equipo desde el admin.
"""

from __future__ import annotations

import json
from datetime import timedelta
from http import HTTPStatus

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.api.permissions import TERMS_NOT_ACCEPTED_MESSAGE
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.adapters import HeadlessAdapter
from urbancheck.users.models import TermsOfService
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

SIGNUP_URL = "/_allauth/app/v1/auth/signup"
CURRENT_TERMS_URL = "/api/terms/current/"
ACCEPT_URL = "/api/users/me/accept-terms/"
ME_URL = "/api/users/me/"
PASSWORD = "Qw8$rTy4&nBv1?"  # noqa: S105


def publish(version: str = "2026-10", **kwargs) -> TermsOfService:
    return TermsOfService.objects.create(
        version=version,
        text=f"Términos {version}",
        **kwargs,
    )


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def accept(user: User, version: str):
    return client_for(user).post(ACCEPT_URL, {"version": version}, format="json")


def signup(client, **extra):
    body = {"email": "vecina@example.com", "password": PASSWORD, "name": "Vecina Uno"}
    body.update(extra)
    return client.post(SIGNUP_URL, json.dumps(body), content_type="application/json")


class TestCurrentTerms:
    def test_without_published_terms_it_is_404(self):
        response = APIClient().get(CURRENT_TERMS_URL)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_returns_the_latest_published_version_without_a_session(self):
        publish("2026-09", published_at=timezone.now() - timedelta(days=30))
        publish("2026-10")

        response = APIClient().get(CURRENT_TERMS_URL)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["version"] == "2026-10"
        assert response.json()["text"] == "Términos 2026-10"

    def test_a_version_scheduled_for_later_is_not_current_yet(self):
        publish("2026-10")
        publish("2026-11", published_at=timezone.now() + timedelta(days=1))

        assert TermsOfService.objects.current().version == "2026-10"


class TestSignup:
    def test_without_published_terms_signing_up_needs_no_acceptance(self, client):
        response = signup(client)

        assert response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}
        user = User.objects.get(email="vecina@example.com")
        assert user.terms_version == ""
        assert user.terms_accepted_at is None

    def test_signing_up_without_accepting_is_rejected(self, client):
        publish()

        response = signup(client)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        params = {e.get("param") for e in response.json()["errors"]}
        assert "accept_terms" in params
        assert not User.objects.filter(email="vecina@example.com").exists()

    def test_accepting_an_outdated_version_is_rejected(self, client):
        publish("2026-10")

        response = signup(client, accept_terms=True, terms_version="2026-09")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        params = {e.get("param") for e in response.json()["errors"]}
        assert "terms_version" in params

    def test_accepting_stores_the_version_and_the_date(self, client):
        publish("2026-10")

        response = signup(client, accept_terms=True, terms_version="2026-10")

        assert response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}
        user = User.objects.get(email="vecina@example.com")
        assert user.terms_version == "2026-10"
        assert user.terms_accepted_at is not None
        assert user.must_accept_terms is False


class TestWhoMustAccept:
    def test_an_existing_citizen_must_accept_newly_published_terms(self):
        citizen = UserFactory.create()
        assert citizen.must_accept_terms is False

        publish()

        assert citizen.must_accept_terms is True

    def test_a_new_version_asks_again(self):
        publish("2026-10")
        citizen = UserFactory.create(
            terms_version="2026-10",
            terms_accepted_at=timezone.now(),
        )
        assert citizen.must_accept_terms is False

        publish("2027-01")

        assert citizen.must_accept_terms is True

    @pytest.mark.parametrize(
        "factory",
        [
            ValidatorFactory,
            OperatorFactory,
            MunicipalAgentFactory,
            PlatformAdminFactory,
        ],
    )
    def test_work_accounts_never_have_to(self, factory):
        publish()

        assert factory.create().must_accept_terms is False

    def test_the_profile_and_the_login_payload_carry_the_flag(self):
        publish()
        citizen = UserFactory.create()

        me = client_for(citizen).get(ME_URL).json()
        payload = HeadlessAdapter().serialize_user(citizen)

        assert me["must_accept_terms"] is True
        assert payload["must_accept_terms"] is True


class TestAcceptOnNextLogin:
    def test_accepting_the_current_version_unblocks_the_account(self):
        publish("2026-10")
        citizen = UserFactory.create()

        response = accept(citizen, "2026-10")

        assert response.status_code == HTTPStatus.OK
        assert response.json()["must_accept_terms"] is False
        citizen.refresh_from_db()
        assert citizen.terms_version == "2026-10"
        assert citizen.terms_accepted_at is not None

    def test_accepting_again_keeps_the_original_date(self):
        publish("2026-10")
        accepted_at = timezone.now() - timedelta(days=5)
        citizen = UserFactory.create(
            terms_version="2026-10",
            terms_accepted_at=accepted_at,
        )

        accept(citizen, "2026-10")

        citizen.refresh_from_db()
        assert citizen.terms_accepted_at == accepted_at

    def test_a_version_that_is_not_current_is_rejected(self):
        publish("2026-10")
        citizen = UserFactory.create()

        response = accept(citizen, "2026-09")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        citizen.refresh_from_db()
        assert citizen.terms_version == ""

    def test_without_published_terms_there_is_nothing_to_accept(self):
        citizen = UserFactory.create()

        response = accept(citizen, "2026-10")

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_work_accounts_cannot_accept(self):
        publish()

        response = accept(ValidatorFactory.create(), "2026-10")

        assert response.status_code == HTTPStatus.FORBIDDEN


class TestParticipationNeedsAcceptance:
    """RN-10 también vale al publicar: el servidor no depende de la app."""

    def test_a_citizen_who_did_not_accept_cannot_like(self):
        publish()
        citizen = UserFactory.create()
        report = ReportFactory.create(municipality=MunicipalityFactory.create())

        response = client_for(citizen).post(f"/api/reports/{report.pk}/like/")

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.json()["detail"] == TERMS_NOT_ACCEPTED_MESSAGE

    def test_after_accepting_the_citizen_can_participate(self):
        publish("2026-10")
        citizen = UserFactory.create(
            terms_version="2026-10",
            terms_accepted_at=timezone.now(),
        )
        report = ReportFactory.create(municipality=MunicipalityFactory.create())

        response = client_for(citizen).post(f"/api/reports/{report.pk}/like/")

        assert response.status_code != HTTPStatus.FORBIDDEN

    def test_reading_is_not_blocked(self):
        publish()
        citizen = UserFactory.create()

        response = client_for(citizen).get("/api/reports/")

        assert response.status_code == HTTPStatus.OK
