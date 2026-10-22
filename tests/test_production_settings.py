"""Lo que ``config.settings.production`` lee del entorno.

Los settings de producción no se pueden importar dentro de la suite, que corre
con ``config.settings.test``: se cargan en un proceso aparte, con un entorno
armado a mano, y se devuelven como JSON. Los valores son de prueba.
"""

import json
import os
import subprocess
import sys

BASE_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": "solo-para-tests",
    "DJANGO_ADMIN_URL": "gestion-tests/",
    "EMAIL_HOST": "smtp.example.test",
}

LOADER = """
import json
import sys

from django.conf import settings

names = sys.argv[1:]
print(json.dumps({name: getattr(settings, name) for name in names}, default=str))
"""


def load(*names: str, without: tuple[str, ...] = (), **env: str):
    """Carga producción en otro proceso con el entorno base, más ``env`` y sin
    ``without``, y devuelve el proceso terminado."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "EMAIL_"))
    }
    environment |= BASE_ENV | env
    for name in without:
        environment.pop(name, None)
    return subprocess.run(  # noqa: S603 (comando fijo, sin entrada externa)
        [sys.executable, "-c", LOADER, *names],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def production_settings(*names: str, **env: str) -> dict:
    """Los settings ``names`` de producción con ``env`` sumado al entorno base."""
    result = load(*names, **env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestEmail:
    """C-02: el SMTP de producción sale del entorno, no solo en local."""

    def test_it_reads_the_smtp_server_and_credentials(self):
        settings = production_settings(
            "EMAIL_HOST",
            "EMAIL_PORT",
            "EMAIL_HOST_USER",
            "EMAIL_HOST_PASSWORD",
            "EMAIL_USE_TLS",
            EMAIL_PORT="2525",
            EMAIL_HOST_USER="usuario-de-prueba",
            EMAIL_HOST_PASSWORD="clave-de-prueba",  # noqa: S106
            EMAIL_USE_TLS="False",
        )

        assert settings == {
            "EMAIL_HOST": "smtp.example.test",
            "EMAIL_PORT": 2525,
            "EMAIL_HOST_USER": "usuario-de-prueba",
            "EMAIL_HOST_PASSWORD": "clave-de-prueba",
            "EMAIL_USE_TLS": False,
        }

    def test_defaults_to_submission_over_tls(self):
        settings = production_settings("EMAIL_PORT", "EMAIL_USE_TLS")

        assert settings == {"EMAIL_PORT": 587, "EMAIL_USE_TLS": True}

    def test_the_server_is_mandatory(self):
        result = load("EMAIL_HOST", without=("EMAIL_HOST",))

        assert result.returncode != 0
        assert "EMAIL_HOST" in result.stderr
