from __future__ import annotations

from factory import Faker
from factory import SubFactory
from factory import post_generation
from factory.django import DjangoModelFactory

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.users.models import User


class UserFactory(DjangoModelFactory[User]):
    email = Faker("email")
    name = Faker("name")

    @post_generation
    def password(self: User, create: bool, extracted: str | None, **kwargs):  # noqa: FBT001
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)
        if create:
            self.save()

    class Meta:
        model = User
        django_get_or_create = ["email"]
        skip_postgeneration_save = True


class PlatformAdminFactory(UserFactory):
    """Administrador de la plataforma: sin municipalidad, opera sobre todas."""

    role = User.Role.ADMIN_PLATAFORMA


class MunicipalAgentFactory(UserFactory):
    role = User.Role.AGENTE_MUNICIPAL
    municipality = SubFactory(MunicipalityFactory)


class ValidatorFactory(UserFactory):
    role = User.Role.VALIDADOR
    municipality = SubFactory(MunicipalityFactory)
