from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory

from urbancheck.users.api.views import UserViewSet

if TYPE_CHECKING:
    from urbancheck.users.models import User


class TestUserViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_get_queryset(self, user: User, api_rf: APIRequestFactory):
        view = UserViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert user in view.get_queryset()

    def test_me_get(self, user: User, api_rf: APIRequestFactory):
        view = UserViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        response = view.me(request)  # type: ignore[call-arg]

        assert response.data["email"] == user.email
        assert response.data["name"] == user.name
        assert response.data["role"] == user.role


class TestUserMePatch:
    def test_patch_name(self, user: User, db):
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.patch(
            "/api/users/me/",
            data={"name": "Nuevo Nombre"},
            format="multipart",
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.name == "Nuevo Nombre"

    def test_patch_email_ignored(self, user: User, db):
        original_email = user.email
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.patch(
            "/api/users/me/",
            data={"email": "hacker@example.com", "name": user.name},
            format="multipart",
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email == original_email
