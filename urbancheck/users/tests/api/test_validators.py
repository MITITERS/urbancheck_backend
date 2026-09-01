"""US-035 — gestión de validadores, por el agente municipal y por el admin."""

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
from urbancheck.users.tests.factories import ValidatorFactory

URL = "/api/validators/"
TEMPORARY_PASSWORD = "Xk7#mP9@qLz2!"

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent() -> User:
    return MunicipalAgentFactory.create(municipality=MunicipalityFactory.create())


@pytest.fixture
def agent_client(agent) -> APIClient:
    client = APIClient()
    client.force_authenticate(agent)
    return client


def payload(**overrides) -> dict:
    return {
        "name": "Validador Uno",
        "email": "validador@muni.gob.ar",
        "temporary_password": TEMPORARY_PASSWORD,
        **overrides,
    }


class TestCreateValidator:
    def test_validator_lands_in_the_municipality_of_the_agent(self, agent_client, agent):
        response = agent_client.post(URL, payload(), format="json")

        assert response.status_code == 201
        validator = User.objects.get(email="validador@muni.gob.ar")
        assert validator.role == User.Role.VALIDADOR
        assert validator.municipality == agent.municipality

    def test_a_municipality_in_the_body_is_ignored(self, agent_client, agent):
        """El agente no elige municipalidad: se le asigna la suya."""
        other = MunicipalityFactory.create()

        agent_client.post(
            URL,
            payload(municipality=other.pk, municipality_id=other.pk),
            format="json",
        )

        validator = User.objects.get(email="validador@muni.gob.ar")
        assert validator.municipality == agent.municipality

    def test_new_validator_must_change_password_and_starts_active(self, agent_client):
        agent_client.post(URL, payload(), format="json")

        validator = User.objects.get(email="validador@muni.gob.ar")
        assert validator.must_change_password is True
        assert validator.is_work_account_active is True
        # Todavía no puede validar: primero tiene que cambiar la contraseña.
        assert validator.can_validate is False


class TestListValidators:
    def test_only_validators_of_my_municipality_are_listed(self, agent_client, agent):
        mine = ValidatorFactory.create(municipality=agent.municipality)
        theirs = ValidatorFactory.create(municipality=MunicipalityFactory.create())

        response = agent_client.get(URL)

        returned = {row["id"] for row in response.data["results"]}
        assert mine.id in returned
        assert theirs.id not in returned

    def test_the_listing_carries_the_avatar(self, agent_client, agent):
        """El panel dibuja la foto en la tabla; sin este campo no la tiene.

        Va como ``None`` cuando la cuenta no subió ninguna, que es lo que el
        panel necesita para caer en las iniciales sin adivinar.
        """
        ValidatorFactory.create(municipality=agent.municipality)

        response = agent_client.get(URL)

        assert response.data["results"][0]["avatar"] is None

    def test_the_listing_carries_state_and_validation_count(self, agent_client, agent):
        validator = ValidatorFactory.create(municipality=agent.municipality)
        report = ReportFactory.create(
            municipality=agent.municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.PENDIENTE_VALIDACION,
            status=Report.Status.REPORTADO,
            changed_by=validator,
        )

        response = agent_client.get(URL)

        row = next(r for r in response.data["results"] if r["id"] == validator.id)
        assert row["validation_count"] == 1
        assert row["is_active_validator"] is True

    def test_agents_and_citizens_are_not_listed(self, agent_client, agent):
        MunicipalAgentFactory.create(municipality=agent.municipality)
        UserFactory.create()

        response = agent_client.get(URL)

        assert all(
            User.objects.get(pk=row["id"]).role == User.Role.VALIDADOR
            for row in response.data["results"]
        )


class TestDeactivation:
    def test_deactivation_removes_the_capability_but_not_the_account(
        self,
        agent_client,
        agent,
    ):
        validator = ValidatorFactory.create(
            municipality=agent.municipality,
            must_change_password=False,
        )
        assert validator.can_validate

        response = agent_client.post(f"{URL}{validator.id}/deactivate/")

        assert response.status_code == 200
        validator.refresh_from_db()
        assert validator.can_validate is False
        # Conserva el acceso como ciudadano común.
        assert validator.is_active is True
        assert validator.role == User.Role.VALIDADOR

    def test_the_validation_history_survives_the_deactivation(self, agent_client, agent):
        validator = ValidatorFactory.create(
            municipality=agent.municipality,
            must_change_password=False,
        )
        report = ReportFactory.create(
            municipality=agent.municipality,
            status=Report.Status.REPORTADO,
            with_history=False,
        )
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.PENDIENTE_VALIDACION,
            status=Report.Status.REPORTADO,
            changed_by=validator,
        )

        response = agent_client.post(f"{URL}{validator.id}/deactivate/")

        assert response.data["validation_count"] == 1
        assert ReportStatusHistory.objects.filter(changed_by=validator).count() == 1

    def test_reactivation_restores_the_capability(self, agent_client, agent):
        validator = ValidatorFactory.create(
            municipality=agent.municipality,
            must_change_password=False,
            is_work_account_active=False,
        )

        response = agent_client.post(f"{URL}{validator.id}/activate/")

        assert response.status_code == 200
        validator.refresh_from_db()
        assert validator.can_validate is True

    def test_cannot_deactivate_a_validator_of_another_municipality(self, agent_client):
        """404 y no 403: el usuario no existe para este agente."""
        foreign = ValidatorFactory.create(municipality=MunicipalityFactory.create())

        response = agent_client.post(f"{URL}{foreign.id}/deactivate/")

        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.is_work_account_active is True


class TestCanValidate:
    """La verificación centralizada que consumen US-036 y US-037."""

    def test_needs_the_three_conditions(self):
        validator = ValidatorFactory.create(must_change_password=False)
        assert validator.can_validate is True

    def test_a_pending_temporary_password_blocks_it(self):
        assert ValidatorFactory.create(must_change_password=True).can_validate is False

    def test_a_deactivated_validator_cannot(self):
        validator = ValidatorFactory.create(
            must_change_password=False,
            is_work_account_active=False,
        )
        assert validator.can_validate is False

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, MunicipalAgentFactory, PlatformAdminFactory],
        ids=["citizen", "agent", "platform_admin"],
    )
    def test_other_roles_cannot(self, factory):
        assert factory.create().can_validate is False


class TestValidatorPermissions:
    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory],
        ids=["citizen", "validator"],
    )
    def test_only_panel_users_manage_validators(self, factory):
        """Ni el vecino ni el propio validador entran a la gestión."""
        client = APIClient()
        client.force_authenticate(factory.create())

        assert client.get(URL).status_code == 403
        assert client.post(URL, payload(), format="json").status_code == 403


class TestPlatformAdminManagesValidators:
    """El admin da altas eligiendo el municipio, y ve los de todos."""

    @pytest.fixture
    def admin_client(self) -> APIClient:
        client = APIClient()
        client.force_authenticate(PlatformAdminFactory.create())
        return client

    def test_the_admin_chooses_the_municipality(self, admin_client):
        municipality = MunicipalityFactory.create()

        response = admin_client.post(
            URL,
            payload(municipality_id=municipality.id),
            format="json",
        )

        assert response.status_code == 201
        validator = User.objects.get(email="validador@muni.gob.ar")
        assert validator.role == User.Role.VALIDADOR
        assert validator.municipality == municipality

    def test_the_municipality_is_required(self, admin_client):
        """Sin jurisdicción propia de la cual derivarla, no hay default posible."""
        response = admin_client.post(URL, payload(), format="json")

        assert response.status_code == 400
        assert "municipality_id" in response.data

    def test_an_unknown_municipality_is_rejected(self, admin_client):
        response = admin_client.post(
            URL,
            payload(municipality_id=999_999),
            format="json",
        )

        assert response.status_code == 400
        assert "municipality_id" in response.data

    def test_the_new_validator_must_change_the_password(self, admin_client):
        municipality = MunicipalityFactory.create()

        admin_client.post(
            URL,
            payload(municipality_id=municipality.id),
            format="json",
        )

        assert User.objects.get(email="validador@muni.gob.ar").must_change_password

    def test_the_admin_sees_validators_of_every_municipality(self, admin_client):
        one, other = MunicipalityFactory.create(), MunicipalityFactory.create()
        mine = ValidatorFactory.create(municipality=one)
        theirs = ValidatorFactory.create(municipality=other)

        ids = {row["id"] for row in admin_client.get(URL).data["results"]}

        assert {mine.id, theirs.id} <= ids

    def test_the_admin_can_filter_by_municipality(self, admin_client):
        one, other = MunicipalityFactory.create(), MunicipalityFactory.create()
        mine = ValidatorFactory.create(municipality=one)
        theirs = ValidatorFactory.create(municipality=other)

        response = admin_client.get(URL, {"municipality": one.id})

        ids = {row["id"] for row in response.data["results"]}
        assert mine.id in ids
        assert theirs.id not in ids

    def test_the_row_says_which_municipality(self, admin_client):
        """Sin esto el admin no puede distinguir filas de municipios distintos."""
        municipality = MunicipalityFactory.create()
        ValidatorFactory.create(municipality=municipality)

        row = admin_client.get(URL).data["results"][0]

        assert row["municipality"]["id"] == municipality.id

    def test_the_admin_can_deactivate_any_validator(self, admin_client):
        validator = ValidatorFactory.create(
            municipality=MunicipalityFactory.create(),
        )

        response = admin_client.post(f"{URL}{validator.id}/deactivate/")

        assert response.status_code == 200
        validator.refresh_from_db()
        assert validator.is_work_account_active is False


class TestTheAgentIsUnaffected:
    """Abrirle la gestión al admin no le cambia nada al agente."""

    def test_the_agent_still_does_not_choose_the_municipality(
        self,
        agent_client,
        agent,
    ):
        """Si manda una ajena en el body, se ignora: manda su jurisdicción."""
        other = MunicipalityFactory.create()

        response = agent_client.post(
            URL,
            payload(municipality_id=other.id),
            format="json",
        )

        assert response.status_code == 201
        assert User.objects.get(
            email="validador@muni.gob.ar",
        ).municipality == agent.municipality

    def test_the_agent_still_sees_only_its_own(self, agent_client, agent):
        mine = ValidatorFactory.create(municipality=agent.municipality)
        theirs = ValidatorFactory.create(municipality=MunicipalityFactory.create())

        ids = {row["id"] for row in agent_client.get(URL).data["results"]}

        assert mine.id in ids
        assert theirs.id not in ids

    def test_the_agent_cannot_reach_a_foreign_validator(self, agent_client):
        theirs = ValidatorFactory.create(municipality=MunicipalityFactory.create())

        response = agent_client.post(f"{URL}{theirs.id}/deactivate/")

        assert response.status_code == 404


class TestArchivedListing:
    """Las dos pestañas del panel: habilitados y archivados.

    Vale para los dos roles que gestionan validadores, cada uno dentro de su
    alcance: el filtro por estado se aplica después del de jurisdicción, no en
    lugar de él.
    """

    @pytest.fixture
    def two_validators(self, agent):
        active = ValidatorFactory.create(
            municipality=agent.municipality,
            name="Validador Activo",
        )
        archived = ValidatorFactory.create(
            municipality=agent.municipality,
            name="Validador Archivado",
            is_work_account_active=False,
        )
        return {"active": active, "archived": archived}

    def test_active_listing_leaves_out_the_archived(self, agent_client, two_validators):
        response = agent_client.get(URL, {"state": "active"})

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {two_validators["active"].id}

    def test_archived_listing_has_only_the_deactivated(
        self,
        agent_client,
        two_validators,
    ):
        response = agent_client.get(URL, {"state": "inactive"})

        returned = {row["id"] for row in response.data["results"]}
        assert returned == {two_validators["archived"].id}

    def test_the_archive_is_still_scoped_by_jurisdiction(
        self,
        agent_client,
        two_validators,
    ):
        """Archivar no es una puerta trasera al personal de otro municipio."""
        foreign = ValidatorFactory.create(
            municipality=MunicipalityFactory.create(),
            is_work_account_active=False,
        )

        response = agent_client.get(URL, {"state": "inactive"})

        assert foreign.id not in {row["id"] for row in response.data["results"]}

    def test_deactivating_moves_the_row_between_listings(
        self,
        agent_client,
        two_validators,
    ):
        validator = two_validators["active"]

        agent_client.post(f"{URL}{validator.id}/deactivate/")

        active = agent_client.get(URL, {"state": "active"}).data["results"]
        archived = agent_client.get(URL, {"state": "inactive"}).data["results"]
        assert validator.id not in {row["id"] for row in active}
        assert validator.id in {row["id"] for row in archived}

    def test_reactivating_from_the_archive_brings_it_back(
        self,
        agent_client,
        two_validators,
    ):
        validator = two_validators["archived"]

        response = agent_client.post(f"{URL}{validator.id}/activate/")

        assert response.status_code == 200
        active = agent_client.get(URL, {"state": "active"}).data["results"]
        assert validator.id in {row["id"] for row in active}

class TestMunicipalityFilterIsForgiving:
    def test_a_municipality_that_is_not_an_id_is_ignored(self):
        """El filtro mal escrito se ignora; antes era un 500.

        Va con el admin y no con el agente: el agente ni siquiera llega a ese
        filtro, porque su listado lo acota la jurisdicción.
        """
        client = APIClient()
        client.force_authenticate(PlatformAdminFactory.create())

        response = client.get(URL, {"municipality": "villa maria"})

        assert response.status_code == 200


class TestValidatorReactivationNeedsAnActiveMunicipality:
    """Misma regla que para el agente: la cuenta trabaja para una municipalidad."""

    def test_reactivating_is_rejected(self, agent_client, agent):
        validator = ValidatorFactory.create(
            municipality=agent.municipality,
            is_work_account_active=False,
        )
        agent.municipality.is_active = False
        agent.municipality.save(update_fields=["is_active"])

        response = agent_client.post(f"{URL}{validator.id}/activate/")

        assert response.status_code == 400
        validator.refresh_from_db()
        assert validator.is_work_account_active is False

    def test_it_works_again_once_the_municipality_is_back(self, agent_client, agent):
        validator = ValidatorFactory.create(
            municipality=agent.municipality,
            is_work_account_active=False,
        )

        response = agent_client.post(f"{URL}{validator.id}/activate/")

        assert response.status_code == 200
        validator.refresh_from_db()
        assert validator.is_work_account_active is True
