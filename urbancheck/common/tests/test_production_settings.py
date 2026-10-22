"""Configuración de producción (Sprint 5, puntos 5.4: SEC-16 y SEC-17).

Se carga ``config.settings.production`` en un proceso aparte, con las
variables obligatorias, para no mezclar sus valores con los de los tests. Es la
misma configuración que corre en el servidor: lo que se verifica acá es lo que
el documento de Seguridad promete.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: Lo que se lee de la configuración, en el proceso hijo.
PROBE = """
import json
from django.conf import settings
print(json.dumps({
    "DEBUG": settings.DEBUG,
    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    "SECURE_SSL_REDIRECT": settings.SECURE_SSL_REDIRECT,
    "SECURE_PROXY_SSL_HEADER": list(settings.SECURE_PROXY_SSL_HEADER),
    "SECURE_HSTS_SECONDS": settings.SECURE_HSTS_SECONDS,
    "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,
    "CSRF_COOKIE_SECURE": settings.CSRF_COOKIE_SECURE,
    "CORS_ALLOWED_ORIGINS": settings.CORS_ALLOWED_ORIGINS,
    "ADMIN_URL": settings.ADMIN_URL,
    "CACHE": settings.CACHES["default"]["BACKEND"],
    "security_logger": "security" in settings.LOGGING["loggers"],
}))
"""


#: Variables del entorno local de desarrollo que no existen en producción: si
#: se heredaran, el test mediría ``.envs/.local`` y no ``production.py``.
LOCAL_ONLY = (
    "DJANGO_ALLOWED_HOSTS",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
)


def production_env(**extra) -> dict[str, str]:
    inherited = {k: v for k, v in os.environ.items() if k not in LOCAL_ONLY}
    env = {
        **inherited,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ADMIN_URL": "gestion-9f2c/",
        "DJANGO_SECURITY_LOG_FILE": "",
        # Obligatoria desde C-02. Un servidor de mentira: nada se envía.
        "EMAIL_HOST": "smtp.example.test",
    }
    env.update(extra)
    return env


def run(args: list[str], **extra) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 (comando fijo, sin entrada externa)
        [sys.executable, *args],
        cwd=ROOT,
        env=production_env(**extra),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


@pytest.fixture(scope="module")
def production():
    result = run(["-c", f"import django; django.setup(){PROBE}"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestProductionSettings:
    def test_debug_is_off_and_hosts_are_bounded(self, production):
        """CP-SEC16-01: ``DEBUG=False`` y ``ALLOWED_HOSTS`` acotado."""
        assert production["DEBUG"] is False
        assert "*" not in production["ALLOWED_HOSTS"]

    def test_https_is_enforced(self, production):
        """CP-SEC16-02: HSTS de un año, redirección SSL, cookies seguras y proxy."""
        assert production["SECURE_SSL_REDIRECT"] is True
        assert production["SECURE_HSTS_SECONDS"] >= 31536000  # noqa: PLR2004
        assert production["SESSION_COOKIE_SECURE"] is True
        assert production["CSRF_COOKIE_SECURE"] is True
        assert production["SECURE_PROXY_SSL_HEADER"] == [
            "HTTP_X_FORWARDED_PROTO",
            "https",
        ]

    def test_cors_is_closed_by_default(self, production):
        """CP-SEC16-03: el panel va por el mismo origen; ningún origen cruzado."""
        assert production["CORS_ALLOWED_ORIGINS"] == []

    def test_the_admin_lives_off_the_default_path(self, production):
        """CP-SEC16-04: la administración en una ruta no predeterminada."""
        assert production["ADMIN_URL"] == "gestion-9f2c/"

    def test_the_default_admin_path_is_refused(self):
        """CP-SEC16-05: ``admin/`` no se acepta ni por descuido."""
        result = run(["-c", "import django; django.setup()"], DJANGO_ADMIN_URL="admin/")

        assert result.returncode != 0
        assert "DJANGO_ADMIN_URL" in result.stderr

    def test_the_security_log_and_the_shared_cache_survive(self, production):
        """CP-SEC16-06: el logger ``security`` y el cache de Redis también en prod."""
        assert production["security_logger"] is True
        assert production["CACHE"] == "django.core.cache.backends.redis.RedisCache"


def test_check_deploy_has_no_warnings():
    """CP-SEC17-01: ``manage.py check --deploy`` sin advertencias."""
    result = run(["manage.py", "check", "--deploy", "--fail-level", "WARNING"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no issues" in result.stdout


#: Los settings del SMTP, en el proceso hijo.
EMAIL_PROBE = """
import json
from django.conf import settings
print(json.dumps({
    name: getattr(settings, name)
    for name in (
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS",
    )
}))
"""


def email_settings(**extra) -> dict:
    result = run(["-c", f"import django; django.setup(){EMAIL_PROBE}"], **extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestEmail:
    """C-02: el SMTP de producción sale del entorno, no solo en local."""

    def test_it_reads_the_smtp_server_and_credentials(self):
        settings = email_settings(
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
        settings = email_settings()

        assert settings["EMAIL_PORT"] == 587  # noqa: PLR2004
        assert settings["EMAIL_USE_TLS"] is True

    def test_the_server_is_mandatory(self):
        env = production_env()
        del env["EMAIL_HOST"]
        result = subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert result.returncode != 0
        assert "EMAIL_HOST" in result.stderr
