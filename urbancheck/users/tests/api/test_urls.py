from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.urls import NoReverseMatch
from django.urls import Resolver404
from django.urls import resolve
from django.urls import reverse

if TYPE_CHECKING:
    from urbancheck.users.models import User


def test_user_detail(user: User):
    assert (
        reverse("api:user-detail", kwargs={"pk": user.pk}) == f"/api/users/{user.pk}/"
    )
    assert resolve(f"/api/users/{user.pk}/").view_name == "api:user-detail"


def test_there_is_no_user_list():
    """C-01: el listado de usuarios no existe."""
    with pytest.raises(NoReverseMatch):
        reverse("api:user-list")
    with pytest.raises(Resolver404):
        resolve("/api/users/")


def test_user_me():
    assert reverse("api:user-me") == "/api/users/me/"
    assert resolve("/api/users/me/").view_name == "api:user-me"
