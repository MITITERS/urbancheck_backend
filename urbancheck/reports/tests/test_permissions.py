"""Permiso de autoría usado por editar/borrar reporte (US-018, US-019) y por
borrar comentario propio (US-009).

Se prueba la clase directamente, sin pasar por la API: los tests de vista ya
cubren el cableado, y acá interesa el contrato del permiso en sí, incluido el
respaldo por ``user_id`` que le permite servir a modelos que no tienen ``author``.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIRequestFactory

from urbancheck.reports.api.permissions import IsAuthorOrReadOnly
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

SAFE = ["get", "head", "options"]
UNSAFE = ["put", "patch", "delete"]


def _request(method: str, user):
    request = getattr(APIRequestFactory(), method)("/")
    request.user = user
    return request


@pytest.mark.django_db
class TestIsAuthorOrReadOnly:
    @pytest.mark.parametrize("method", SAFE)
    def test_safe_methods_are_allowed_for_anyone(self, method):
        report = ReportFactory.create()
        permission = IsAuthorOrReadOnly()
        request = _request(method, UserFactory.create())
        assert permission.has_object_permission(request, None, report) is True

    @pytest.mark.parametrize("method", UNSAFE)
    def test_author_may_write(self, method):
        author = UserFactory.create()
        report = ReportFactory.create(author=author)
        permission = IsAuthorOrReadOnly()
        assert permission.has_object_permission(_request(method, author), None, report)

    @pytest.mark.parametrize("method", UNSAFE)
    def test_other_user_may_not_write(self, method):
        report = ReportFactory.create()
        permission = IsAuthorOrReadOnly()
        request = _request(method, UserFactory.create())
        assert permission.has_object_permission(request, None, report) is False

    def test_applies_to_comments_too(self):
        """El mismo permiso protege ``DELETE /api/comments/{id}/``."""
        author = UserFactory.create()
        comment = CommentFactory.create(author=author)
        permission = IsAuthorOrReadOnly()
        assert permission.has_object_permission(
            _request("delete", author), None, comment,
        )
        other = _request("delete", UserFactory.create())
        assert permission.has_object_permission(other, None, comment) is False

    def test_falls_back_to_user_id(self):
        """Objetos sin ``author`` (como Like) se resuelven por ``user_id``."""
        owner = UserFactory.create()
        like = LikeFactory.create(user=owner)
        permission = IsAuthorOrReadOnly()
        assert permission.has_object_permission(_request("delete", owner), None, like)
        other = _request("delete", UserFactory.create())
        assert permission.has_object_permission(other, None, like) is False

    def test_message_is_explicit(self):
        """El cliente muestra este texto tal cual en el 403."""
        assert "autor" in IsAuthorOrReadOnly.message.lower()
