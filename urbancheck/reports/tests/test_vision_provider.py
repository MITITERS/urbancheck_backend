"""US-015 — la interfaz del servicio de visión y su proveedor nulo por defecto.

``VISION_PROVIDER`` vacío es el default del producto: la comparación no se
ejecuta, ninguna foto sale del servidor y cada cierre figura como
"comparación no disponible". El equipo eligió Gemini, que entra por el
adaptador ``openai_compatible`` con su clave en una variable de entorno.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from urbancheck.reports import vision
from urbancheck.reports.comparison import register_comparison
from urbancheck.reports.models import ResolutionComparison
from urbancheck.reports.tests.factories import ResolutionEvidenceFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append(args)
        msg = "No debería salir nada a la red."
        raise AssertionError(msg)

    monkeypatch.setattr(vision.requests, "post", post)
    return calls


class TestTheNullProvider:
    def test_it_is_the_default(self):
        """CP-015-11: sin configurar nada, el proveedor es el nulo."""
        from config.settings import base  # noqa: PLC0415

        assert base.VISION_PROVIDER == ""

    def test_it_never_compares(self, settings):
        """CP-015-12: el nulo no está configurado y no compara."""
        settings.VISION_PROVIDER = ""

        provider = vision.get_provider()

        assert isinstance(provider, vision.NullVisionProvider)
        assert not vision.is_configured()
        with pytest.raises(vision.VisionError) as caught:
            vision.compare_images(b"a", b"b", category="bache", description="")
        assert caught.value.code == "no_provider"

    def test_a_closure_is_registered_as_unavailable_and_nothing_is_sent(
        self,
        settings,
        no_network,
    ):
        """CP-015-13: con el nulo, el cierre queda "no disponible" y nada sale."""
        settings.VISION_PROVIDER = ""
        evidence = ResolutionEvidenceFactory.create()

        comparison = register_comparison(evidence)

        assert comparison.status == ResolutionComparison.Status.UNAVAILABLE
        assert comparison.failure_reason == "not_configured"
        assert no_network == []


class TestTheChosenProvider:
    def test_the_openai_compatible_adapter_needs_its_key(self, settings):
        """CP-015-14: el adaptador elegido sin clave queda apagado."""
        settings.VISION_PROVIDER = "openai_compatible"
        settings.RESOLUTION_COMPARISON_API_KEY = ""

        assert isinstance(vision.get_provider(), vision.OpenAICompatibleProvider)
        assert not vision.is_configured()

        settings.RESOLUTION_COMPARISON_API_KEY = "clave"
        assert vision.is_configured()

    def test_an_unknown_provider_fails_loudly(self, settings):
        """CP-015-15: un nombre mal escrito no se toma por el nulo en silencio."""
        settings.VISION_PROVIDER = "gemini"

        with pytest.raises(ImproperlyConfigured, match="openai_compatible"):
            vision.get_provider()
