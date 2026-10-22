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
    """Todo lo que se escribe en un test cae en el tmpdir, publicado o no.

    El storage privado de US-042 se redirige igual que ``MEDIA_ROOT``, o los
    tests dejarían originales sin difuminar en el directorio real del proyecto.
    Alcanza con mover ``PENDING_PHOTO_ROOT``: ``PendingPhotoStorage`` lee su
    ubicación de settings en cada uso, justamente para que esto funcione.
    """
    # Hermanos, nunca anidados: en producción `PENDING_PHOTO_ROOT` está fuera
    # de `MEDIA_ROOT` justamente para que `/media/` no lo alcance, y un test
    # que los anide no estaría probando esa separación.
    settings.MEDIA_ROOT = tmpdir.mkdir("media").strpath
    settings.PENDING_PHOTO_ROOT = tmpdir.mkdir("pending").strpath


@pytest.fixture(autouse=True)
def _no_geocoding_network(monkeypatch) -> None:
    """Impide que los tests golpeen la red real de Nominatim ni la de Georef.

    Por defecto la geocodificación queda sin resultados (``search_addresses`` captura
    RequestException y devuelve ``[]``). Los tests que la ejercitan parchean
    ``urbancheck.reports.geocoding.requests.get`` explícitamente. Limpiamos la caché
    para que un resultado cacheado no se filtre entre tests.
    """

    def _blocked(*args, **kwargs):
        msg = "Network disabled in tests"
        raise requests.RequestException(msg)

    monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", _blocked)
    # Mismo criterio para el catálogo de provincias y localidades: ningún test
    # debe salir a la red real.
    monkeypatch.setattr("urbancheck.municipalities.georef.requests.get", _blocked)
    # Ni el servicio de visión de la comparación de cierres (US-015).
    monkeypatch.setattr("urbancheck.reports.vision.requests.post", _blocked)
    cache.clear()


@pytest.fixture(autouse=True)
def _no_comparison_broker(monkeypatch) -> None:
    """Impide que un cierre en un test encole la comparación en el Redis real.

    La comparación de US-015 se encola al commitear el cierre. Los tests que la
    ejercitan la corren explícitamente o reemplazan ``delay`` con su propio
    registro; el resto no tiene por qué enterarse.
    """
    from urbancheck.reports.tasks import compare_resolution  # noqa: PLC0415

    monkeypatch.setattr(compare_resolution, "delay", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _no_anonymization_broker(monkeypatch) -> None:
    """Impide que una carga de foto en un test encole el difuminado en Redis.

    Mismo criterio que ``_no_comparison_broker``: el que ejercita US-042 corre
    la tarea explícitamente con ``.apply(...)``, o usa ``process_pending_photos``.
    """
    from urbancheck.anonymization.tasks import anonymize_photo  # noqa: PLC0415

    monkeypatch.setattr(anonymize_photo, "delay", lambda *args, **kwargs: None)


@pytest.fixture
def process_pending_photos(django_capture_on_commit_callbacks):
    """Corre el difuminado de todo lo que haya quedado en cola.

    Es el puente entre "el endpoint ya contestó" y "el reporte ya es público",
    que en producción los separa un worker y en un test no separa nada.

    Ejecuta también los ``on_commit`` que deja el pipeline —el borrado de la
    original y el disparo de la comparación de US-015—: sin eso el test vería
    un estado intermedio que en producción no existe, con la foto ya publicada
    y la original todavía en el storage privado.
    """
    from django.apps import apps as django_apps  # noqa: PLC0415

    from urbancheck.anonymization.models import PendingPhotoMixin  # noqa: PLC0415
    from urbancheck.anonymization.models import PhotoStatus  # noqa: PLC0415
    from urbancheck.anonymization.tasks import anonymize_photo  # noqa: PLC0415

    def _run() -> int:
        processed = 0
        with django_capture_on_commit_callbacks(execute=True):
            for model in django_apps.get_models():
                if not issubclass(model, PendingPhotoMixin):
                    continue
                pending = model.objects.filter(
                    photo_status=PhotoStatus.PENDIENTE,
                ).exclude(photo_pending="")
                for pk in list(pending.values_list("pk", flat=True)):
                    anonymize_photo.apply(args=[model._meta.label_lower, pk])  # noqa: SLF001
                    processed += 1
        return processed

    return _run


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
