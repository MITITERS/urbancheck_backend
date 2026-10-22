"""El despliegue de producción: scripts de arranque, Compose y Traefik.

Son archivos de configuración y no código, pero un error en ellos no lo ve
ningún otro test: se nota recién en el servidor.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DJANGO = ROOT / "compose" / "production" / "django"


def commands(script: Path) -> list[str]:
    """Las líneas que ejecuta un script, sin comentarios ni vacías."""
    return [
        line.strip()
        for line in script.read_text().splitlines()
        if line.strip() and not line.strip().startswith(("#", "set "))
    ]


class TestMigrationsOnStart:
    """C-03: el servicio django migra antes de servir."""

    def test_django_migrates_before_collectstatic(self):
        lines = commands(DJANGO / "start")
        migrate = next(i for i, line in enumerate(lines) if " migrate " in f"{line} ")
        collect = next(i for i, line in enumerate(lines) if "collectstatic" in line)

        assert "--noinput" in lines[migrate]
        assert migrate < collect

    def test_celery_services_do_not_migrate(self):
        for service in ("worker", "beat", "flower"):
            script = DJANGO / "celery" / service / "start"
            assert "migrate" not in script.read_text(), service
