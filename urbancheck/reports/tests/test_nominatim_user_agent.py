"""N-15: el User-Agent de Nominatim identifica al proyecto, no a una persona.

La política de uso de Nominatim pide un User-Agent que identifique la
aplicación; el default llevaba el correo personal de un integrante.
"""

from pathlib import Path

from django.conf import settings

EXPECTED = "UrbanCheck/1.0 (+https://urbancheck.com.ar)"
ROOT = Path(__file__).resolve().parents[3]


def test_the_default_user_agent_is_the_projects():
    assert settings.NOMINATIM_USER_AGENT == EXPECTED
    assert "@" not in settings.NOMINATIM_USER_AGENT


def test_the_env_example_documents_the_same_value():
    lines = (ROOT / ".env.example").read_text().splitlines()

    assert f"NOMINATIM_USER_AGENT={EXPECTED}" in lines
