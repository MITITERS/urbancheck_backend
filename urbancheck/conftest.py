from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import requests
from django.core.cache import cache

from urbancheck.users.tests.factories import UserFactory

if TYPE_CHECKING:
    from urbancheck.users.models import User


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture(autouse=True)
def _no_geocoding_network(monkeypatch) -> None:
    """Impide que los tests golpeen la red real de Nominatim.

    Por defecto la geocodificación queda sin resultados (``search_addresses`` captura
    RequestException y devuelve ``[]``). Los tests que la ejercitan parchean
    ``urbancheck.reports.geocoding.requests.get`` explícitamente. Limpiamos la caché
    para que un resultado cacheado no se filtre entre tests.
    """

    def _blocked(*args, **kwargs):
        raise requests.RequestException("Network disabled in tests")

    monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", _blocked)
    cache.clear()


@pytest.fixture
def user(db) -> User:
    return UserFactory.create()
