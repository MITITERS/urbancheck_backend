from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import requests
from django.core.cache import cache

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.users.tests.factories import UserFactory

if TYPE_CHECKING:
    from urbancheck.municipalities.models import Municipality
    from urbancheck.users.models import User


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture(autouse=True)
def _no_geocoding_network(monkeypatch) -> None:
    """Impide que los tests golpeen la red real de Nominatim ni la de Georef.

    Por defecto la geocodificación queda sin resultados (``search_addresses`` captura
    RequestException y devuelve ``[]``). Los tests que la ejercitan parchean
    ``urbancheck.reports.geocoding.requests.get`` explícitamente. Limpiamos la caché
    para que un resultado cacheado no se filtre entre tests.
    """

    def _blocked(*args, **kwargs):
        raise requests.RequestException("Network disabled in tests")

    monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", _blocked)
    # Mismo criterio para el catálogo de provincias y localidades: ningún test
    # debe salir a la red real.
    monkeypatch.setattr("urbancheck.municipalities.georef.requests.get", _blocked)
    cache.clear()


@pytest.fixture(autouse=True)
def active_municipality(db, settings) -> Municipality:
    """La plataforma siempre opera con una municipalidad activa (US-034).

    Es autouse porque crear un reporte la necesita, y crear reportes es algo que
    hace medio repositorio. Fija además ``ACTIVE_MUNICIPALITY_ID`` para que la
    resolución sea determinística aunque el test dé de alta más municipios: sin
    eso, un test con dos municipalidades haría fallar la creación por ambigua.
    """
    # Nombre por secuencia: un nombre fijo chocaría con los tests que dan de
    # alta municipalidades por su cuenta.
    municipality = MunicipalityFactory.create()
    settings.ACTIVE_MUNICIPALITY_ID = municipality.pk
    return municipality


@pytest.fixture
def user(db) -> User:
    return UserFactory.create()
