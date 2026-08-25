"""US-017 — alta de agentes municipales por el admin de la plataforma."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory

URL = "/api/municipal-agents/"
TEMPORARY_PASSWORD = "Xk7#mP9@qLz2!"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(PlatformAdminFactory.create())
    return client


def payload(municipality, **overrides) -> dict:
    return {
        "name": "Agente Uno",
        "email": "agente@muni.gob.ar",
        "temporary_password": TEMPORARY_PASSWORD,
        "municipality_id": municipality.pk,
        **overrides,
    }


class TestCreateMunicipalAgent:
    def test_creates_an_agent_bound_to_the_municipality(self, admin_client):
        municipality = MunicipalityFactory.create()

        response = admin_client.post(URL, payload(municipality), format="json")

        assert response.status_code == 201
        agent = User.objects.get(email="agente@muni.gob.ar")
        assert agent.role == User.Role.AGENTE_MUNICIPAL
        assert agent.municipality == municipality
        assert agent.is_panel_user

    def test_new_agent_must_change_password(self, admin_client):
        response = admin_client.post(
            URL,
            payload(MunicipalityFactory.create()),
            format="json",
        )

        assert response.data["must_change_password"] is True
        assert User.objects.get(email="agente@muni.gob.ar").must_change_password

    def test_temporary_password_is_usable_and_never_echoed(self, admin_client):
        admin_client.post(URL, payload(MunicipalityFactory.create()), format="json")

        agent = User.objects.get(email="agente@muni.gob.ar")
        assert agent.check_password(TEMPORARY_PASSWORD)

    def test_response_does_not_leak_the_password(self, admin_client):
        response = admin_client.post(
            URL,
            payload(MunicipalityFactory.create()),
            format="json",
        )

        assert "temporary_password" not in response.data
        assert "password" not in response.data

    def test_duplicate_email_is_rejected(self, admin_client):
        UserFactory.create(email="agente@muni.gob.ar")

        response = admin_client.post(
            URL,
            payload(MunicipalityFactory.create()),
            format="json",
        )

        assert response.status_code == 400
        assert "email" in response.data

    def test_weak_temporary_password_is_rejected(self, admin_client):
        response = admin_client.post(
            URL,
            payload(MunicipalityFactory.create(), temporary_password="123"),
            format="json",
        )

        assert response.status_code == 400
        assert "temporary_password" in response.data

    def test_municipality_is_required(self, admin_client):
        body = payload(MunicipalityFactory.create())
        del body["municipality_id"]

        response = admin_client.post(URL, body, format="json")

        assert response.status_code == 400
        assert "municipality_id" in response.data


class TestMunicipalAgentPermissions:
    @pytest.mark.parametrize(
        "factory",
        [UserFactory, MunicipalAgentFactory],
        ids=["citizen", "municipal_agent"],
    )
    def test_only_the_platform_admin_can_create_agents(self, factory):
        client = APIClient()
        client.force_authenticate(factory.create())

        response = client.post(
            URL,
            payload(MunicipalityFactory.create()),
            format="json",
        )

        assert response.status_code == 403
        assert not User.objects.filter(email="agente@muni.gob.ar").exists()
