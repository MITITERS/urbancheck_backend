"""Adapters de allauth: qué se abre al registro y qué usuario devuelve el login.

El ``HeadlessAdapter`` es el que hace posible el flujo de US-017: el panel decide
a dónde mandar a quien acaba de ingresar —al cambio de contraseña o a su
sección— con la respuesta del propio login, sin una llamada extra.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from urbancheck.users.adapters import AccountAdapter
from urbancheck.users.adapters import HeadlessAdapter
from urbancheck.users.adapters import SocialAccountAdapter
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def request_():
    return RequestFactory().get("/")


class TestSignupIsOpen:
    """El registro se abre o se cierra desde un único setting."""

    def test_the_account_adapter_follows_the_setting(self, request_, settings):
        settings.ACCOUNT_ALLOW_REGISTRATION = False

        assert AccountAdapter().is_open_for_signup(request_) is False

    def test_the_account_adapter_allows_it_by_default(self, request_, settings):
        settings.ACCOUNT_ALLOW_REGISTRATION = True

        assert AccountAdapter().is_open_for_signup(request_) is True

    def test_the_social_adapter_follows_the_same_setting(self, request_, settings):
        # Los dos caminos de alta se cierran juntos: si no, cerrar el registro
        # dejaría abierta la puerta de atrás.
        settings.ACCOUNT_ALLOW_REGISTRATION = False

        assert SocialAccountAdapter().is_open_for_signup(request_, None) is False


class TestSocialPopulateUser:
    """El nombre que llega del proveedor social, con sus tres formas."""

    def _populate(self, monkeypatch, data):
        adapter = SocialAccountAdapter()
        # El adapter base arma el usuario a partir del proveedor; acá interesa
        # solo lo que agrega el nuestro encima.
        monkeypatch.setattr(
            "allauth.socialaccount.adapter.DefaultSocialAccountAdapter.populate_user",
            lambda self, request, sociallogin, data: User(email=data.get("email", "")),
        )
        return adapter.populate_user(None, None, data)

    def test_it_takes_the_full_name_when_the_provider_sends_it(self, monkeypatch):
        user = self._populate(monkeypatch, {"name": "Ana Agente"})

        assert user.name == "Ana Agente"

    def test_it_joins_first_and_last_name_when_there_is_no_full_name(self, monkeypatch):
        user = self._populate(monkeypatch, {"first_name": "Ana", "last_name": "Agente"})

        assert user.name == "Ana Agente"

    def test_a_first_name_alone_is_enough(self, monkeypatch):
        user = self._populate(monkeypatch, {"first_name": "Ana"})

        assert user.name == "Ana"

    def test_without_any_name_it_leaves_the_field_empty(self, monkeypatch):
        user = self._populate(monkeypatch, {})

        assert not user.name


class TestHeadlessSerializeUser:
    """Lo que el login devuelve del usuario, que es con lo que arranca el panel."""

    def test_it_adds_the_role(self):
        agent = MunicipalAgentFactory.create()

        data = HeadlessAdapter().serialize_user(agent)

        assert data["role"] == User.Role.AGENTE_MUNICIPAL

    def test_it_adds_the_temporary_password_flag(self):
        # Es lo que hace que el panel mande al cambio de contraseña sin pedirle
        # el perfil al servidor.
        agent = MunicipalAgentFactory.create(must_change_password=True)

        data = HeadlessAdapter().serialize_user(agent)

        assert data["must_change_password"] is True

    def test_it_adds_the_municipality_with_city_and_province(self):
        agent = MunicipalAgentFactory.create()

        data = HeadlessAdapter().serialize_user(agent)

        assert data["municipality"] == {
            "id": agent.municipality.pk,
            "city": agent.municipality.city,
            "province": agent.municipality.province,
        }

    def test_a_user_without_municipality_gets_an_explicit_null(self):
        """Que llegue en ``null`` es información, no ausencia de dato.

        El adapter por defecto descarta las claves vacías; el administrador de
        la plataforma no tiene jurisdicción y el panel necesita saberlo.
        """
        admin = PlatformAdminFactory.create()

        data = HeadlessAdapter().serialize_user(admin)

        assert "municipality" in data
        assert data["municipality"] is None

    def test_a_citizen_is_serialized_as_such(self):
        citizen = UserFactory.create()

        data = HeadlessAdapter().serialize_user(citizen)

        assert data["role"] == User.Role.CIUDADANO
        assert data["municipality"] is None
        assert data["must_change_password"] is False
