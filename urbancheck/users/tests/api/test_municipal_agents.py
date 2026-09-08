"""US-017 — alta y baja lógica de agentes municipales, por el admin."""

import pytest
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportFactory
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


class TestDeactivateMunicipalAgent:
    """Baja lógica del agente: pierde el panel, conserva la cuenta.

    Es el mismo tablero que el del validador, y por eso la misma baja: no se
    borra el registro ni se le cierra la cuenta, así que lo que gestionó sigue
    en el historial de cada reporte con su nombre.
    """

    @pytest.fixture
    def agent(self):
        return MunicipalAgentFactory.create(must_change_password=False)

    def test_deactivating_takes_the_panel_away(self, admin_client, agent):
        response = admin_client.post(f"{URL}{agent.id}/deactivate/")

        assert response.status_code == 200
        assert response.data["is_active_agent"] is False
        agent.refresh_from_db()
        assert agent.can_operate_panel is False

    def test_the_deactivated_agent_gets_403_from_the_panel(self, admin_client, agent):
        admin_client.post(f"{URL}{agent.id}/deactivate/")
        agent.refresh_from_db()

        client = APIClient()
        client.force_authenticate(agent)

        # No es una pantalla: es todo el panel, porque la baja se verifica en el
        # permiso base y no endpoint por endpoint.
        assert client.get("/api/panel/reports/").status_code == 403
        assert client.get("/api/validators/").status_code == 403

    def test_the_account_survives_and_can_still_sign_in(self, admin_client, agent):
        admin_client.post(f"{URL}{agent.id}/deactivate/")
        agent.refresh_from_db()

        # La cuenta de Django sigue activa: el panel le explica qué pasó en vez
        # de rebotarle el login como si la contraseña estuviera mal.
        assert agent.is_active is True
        assert User.objects.filter(pk=agent.pk).exists()

    def test_the_management_history_survives(self, admin_client, agent):
        report = ReportFactory.create(municipality=agent.municipality)
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.REPORTADO,
            status=Report.Status.EN_PROCESO,
            changed_by=agent,
        )

        response = admin_client.post(f"{URL}{agent.id}/deactivate/")

        assert response.data["management_count"] == 1
        assert ReportStatusHistory.objects.filter(changed_by=agent).count() == 1

    def test_reactivation_gives_the_panel_back(self, admin_client, agent):
        agent.is_work_account_active = False
        agent.save(update_fields=["is_work_account_active"])

        response = admin_client.post(f"{URL}{agent.id}/activate/")

        assert response.status_code == 200
        agent.refresh_from_db()
        assert agent.can_operate_panel is True

    def test_the_listing_carries_the_state(self, admin_client, agent):
        response = admin_client.get(URL)

        row = response.data["results"][0]
        assert row["is_active_agent"] is True
        assert row["management_count"] == 0

    def test_the_listing_carries_the_avatar(self, admin_client, agent):
        """El panel dibuja la foto en la tabla; sin este campo no la tiene.

        Va como ``None`` cuando la cuenta no subió ninguna, que es lo que el
        panel necesita para caer en las iniciales sin adivinar.
        """
        response = admin_client.get(URL)

        assert response.data["results"][0]["avatar"] is None

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, MunicipalAgentFactory],
        ids=["citizen", "another_agent"],
    )
    def test_only_the_platform_admin_deactivates(self, factory, agent):
        """Un agente no puede dar de baja a otro: eso lo decide la plataforma."""
        client = APIClient()
        client.force_authenticate(factory.create(must_change_password=False))

        assert client.post(f"{URL}{agent.id}/deactivate/").status_code == 403
        agent.refresh_from_db()
        assert agent.is_work_account_active is True


class TestArchivedListing:
    """El panel separa en dos pestañas, y el filtro vive en el servidor.

    Que la cuenta archivada no aparezca en la principal no alcanza con
    esconderla en el cliente: no tiene que viajar siquiera, o con veinte filas
    por página las bajas se comen el lugar de las cuentas que sí trabajan.
    """

    @pytest.fixture
    def two_agents(self):
        active = MunicipalAgentFactory.create(name="Agente Activo")
        archived = MunicipalAgentFactory.create(
            name="Agente Archivado",
            is_work_account_active=False,
        )
        return {"active": active, "archived": archived}

    def test_active_listing_leaves_out_the_archived(self, admin_client, two_agents):
        response = admin_client.get(URL, {"state": "active"})

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {two_agents["active"].id}

    def test_archived_listing_has_only_the_deactivated(self, admin_client, two_agents):
        response = admin_client.get(URL, {"state": "inactive"})

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {two_agents["archived"].id}

    def test_without_the_filter_both_are_listed(self, admin_client, two_agents):
        """Compatibilidad: es lo que hacía el listado antes de existir el filtro."""
        response = admin_client.get(URL)

        assert response.data["count"] == 2

    def test_an_unknown_state_does_not_filter_nor_break(self, admin_client, two_agents):
        response = admin_client.get(URL, {"state": "cualquiera"})

        assert response.status_code == 200
        assert response.data["count"] == 2

    def test_deactivating_moves_the_row_between_listings(
        self,
        admin_client,
        two_agents,
    ):
        agent = two_agents["active"]

        admin_client.post(f"{URL}{agent.id}/deactivate/")

        active = admin_client.get(URL, {"state": "active"}).data["results"]
        archived = admin_client.get(URL, {"state": "inactive"}).data["results"]
        assert agent.id not in {row["id"] for row in active}
        assert agent.id in {row["id"] for row in archived}

    def test_reactivating_from_the_archive_brings_it_back(
        self,
        admin_client,
        two_agents,
    ):
        """Reactivar tiene que alcanzar a una cuenta que el listado principal no ve."""
        agent = two_agents["archived"]

        response = admin_client.post(f"{URL}{agent.id}/activate/")

        assert response.status_code == 200
        active = admin_client.get(URL, {"state": "active"}).data["results"]
        assert agent.id in {row["id"] for row in active}


class TestFilterByMunicipality:
    """``?municipality=<id>``: el admin ve todos, y elige mirar de a uno."""

    @pytest.fixture
    def two_cities(self):
        villa_maria = MunicipalityFactory.create(city="Villa María")
        bell_ville = MunicipalityFactory.create(city="Bell Ville")
        return {
            "villa_maria": villa_maria,
            "bell_ville": bell_ville,
            "local": MunicipalAgentFactory.create(municipality=villa_maria),
            "foreign": MunicipalAgentFactory.create(municipality=bell_ville),
        }

    def test_only_the_agents_of_that_municipality(self, admin_client, two_cities):
        response = admin_client.get(
            URL,
            {"municipality": two_cities["villa_maria"].pk},
        )

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {two_cities["local"].id}

    def test_it_combines_with_the_state(self, admin_client, two_cities):
        """Los dos filtros se suman: son dos cortes de la misma lista."""
        admin_client.post(f"{URL}{two_cities['local'].id}/deactivate/")

        active = admin_client.get(
            URL,
            {"municipality": two_cities["villa_maria"].pk, "state": "active"},
        )
        archived = admin_client.get(
            URL,
            {"municipality": two_cities["villa_maria"].pk, "state": "inactive"},
        )

        assert active.data["count"] == 0
        assert {row["id"] for row in archived.data["results"]} == {
            two_cities["local"].id,
        }

    def test_without_the_filter_the_admin_sees_every_municipality(
        self,
        admin_client,
        two_cities,
    ):
        response = admin_client.get(URL)

        assert response.data["count"] == 2

    def test_a_municipality_that_is_not_an_id_is_ignored(
        self,
        admin_client,
        two_cities,
    ):
        """Un parámetro mal escrito no puede tumbar el listado."""
        response = admin_client.get(URL, {"municipality": "villa maria"})

        assert response.status_code == 200
        assert response.data["count"] == 2


class TestReactivationNeedsAnActiveMunicipality:
    """No se reactiva a nadie cuyo municipio esté dado de baja.

    Es el complemento de la cascada: si dar de baja el municipio archiva a su
    personal, poder reactivarlo de a uno dejaría exactamente el estado que la
    cascada existe para evitar —una cuenta operando sobre una jurisdicción
    cerrada—.
    """

    @pytest.fixture
    def archived_with_its_municipality(self, admin_client):
        municipality = MunicipalityFactory.create()
        agent = MunicipalAgentFactory.create(municipality=municipality)
        admin_client.delete(f"/api/municipalities/{municipality.pk}/")
        agent.refresh_from_db()
        return {"municipality": municipality, "agent": agent}

    def test_reactivating_is_rejected(
        self,
        admin_client,
        archived_with_its_municipality,
    ):
        agent = archived_with_its_municipality["agent"]

        response = admin_client.post(f"{URL}{agent.id}/activate/")

        assert response.status_code == 400
        agent.refresh_from_db()
        assert agent.is_work_account_active is False

    def test_the_message_says_what_to_do_next(
        self,
        admin_client,
        archived_with_its_municipality,
    ):
        agent = archived_with_its_municipality["agent"]

        response = admin_client.post(f"{URL}{agent.id}/activate/")

        assert "municipalidad está dada de baja" in response.data["detail"]

    def test_it_works_again_once_the_municipality_is_back(
        self,
        admin_client,
        archived_with_its_municipality,
    ):
        municipality = archived_with_its_municipality["municipality"]
        municipality.is_active = True
        municipality.save(update_fields=["is_active"])
        agent = archived_with_its_municipality["agent"]

        response = admin_client.post(f"{URL}{agent.id}/activate/")

        assert response.status_code == 200
        agent.refresh_from_db()
        assert agent.is_work_account_active is True

    def test_deactivating_is_always_allowed(self, admin_client):
        """La regla es solo para reactivar: dar de baja nunca puede quedar trabado."""
        municipality = MunicipalityFactory.create()
        agent = MunicipalAgentFactory.create(municipality=municipality)
        municipality.is_active = False
        municipality.save(update_fields=["is_active"])

        response = admin_client.post(f"{URL}{agent.id}/deactivate/")

        assert response.status_code == 200
