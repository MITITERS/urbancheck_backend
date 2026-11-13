"""US-017 — regla de municipalidad obligatoria según el rol."""

import pytest
from django.core.exceptions import ValidationError

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.users.models import User

pytestmark = pytest.mark.django_db

MUNICIPALITY_BOUND = [User.Role.AGENTE_MUNICIPAL, User.Role.VALIDADOR]
MUNICIPALITY_FREE = [User.Role.CIUDADANO, User.Role.ADMIN_PLATAFORMA]


@pytest.mark.parametrize("role", MUNICIPALITY_BOUND)
def test_bound_role_without_municipality_is_invalid(role):
    user = User(email=f"{role}@test.com", role=role)

    with pytest.raises(ValidationError) as exc:
        user.full_clean(exclude=["password"])

    assert "municipality" in exc.value.error_dict


@pytest.mark.parametrize("role", MUNICIPALITY_FREE)
def test_free_role_with_municipality_is_invalid(role):
    user = User(
        email=f"{role}@test.com",
        role=role,
        municipality=MunicipalityFactory.create(),
    )

    with pytest.raises(ValidationError) as exc:
        user.full_clean(exclude=["password"])

    assert "municipality" in exc.value.error_dict


@pytest.mark.parametrize("role", MUNICIPALITY_BOUND)
def test_bound_role_with_municipality_is_valid(role):
    user = User(
        email=f"{role}@test.com",
        role=role,
        municipality=MunicipalityFactory.create(),
    )

    user.full_clean(exclude=["password"])


def test_citizen_is_the_default_role():
    assert User(email="a@b.com").role == User.Role.CIUDADANO


def test_superuser_counts_as_platform_admin():
    """Es lo que hace arrancable el sistema: alguien tiene que crear el primer
    municipio antes de que exista un usuario con el rol."""
    user = User(email="root@test.com", is_superuser=True)

    assert user.is_platform_admin
    assert user.is_panel_user
