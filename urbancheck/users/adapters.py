from __future__ import annotations

import typing

from allauth.account.adapter import DefaultAccountAdapter
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings

if typing.TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.http import HttpRequest

    from urbancheck.users.models import User


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
    ) -> bool:
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)

    def populate_user(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
        data: dict[str, typing.Any],
    ) -> User:
        """
        Populates user information from social provider info.

        See: https://docs.allauth.org/en/latest/socialaccount/advanced.html#creating-and-populating-user-instances
        """
        user = super().populate_user(request, sociallogin, data)
        if not user.name:
            if name := data.get("name"):
                user.name = name
            elif first_name := data.get("first_name"):
                user.name = first_name
                if last_name := data.get("last_name"):
                    user.name += f" {last_name}"
        return user


class HeadlessAdapter(DefaultHeadlessAdapter):
    """Payload de usuario que devuelve allauth headless.

    El panel necesita el rol, la municipalidad y el flag de contraseña temporal
    en la respuesta del login para decidir el flujo sin una llamada extra
    (US-017). El adapter por defecto además descarta las claves con valor vacío
    o nulo, así que ``municipality`` se agrega después del filtrado: que llegue
    en ``null`` es información, no ausencia de dato.
    """

    def serialize_user(self, user) -> dict[str, typing.Any]:
        data = super().serialize_user(user)
        municipality = getattr(user, "municipality", None)
        data["role"] = user.role
        data["must_change_password"] = user.must_change_password
        data["municipality"] = (
            {
                "id": municipality.pk,
                "city": municipality.city,
                "province": municipality.province,
            }
            if municipality
            else None
        )
        return data
