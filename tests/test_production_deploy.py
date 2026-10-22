"""El despliegue de producción: scripts de arranque, Compose y Traefik.

Son archivos de configuración y no código, pero un error en ellos no lo ve
ningún otro test: se nota recién en el servidor.
"""

import re
from pathlib import Path

import yaml

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


DOMAIN = "ejemplo.test"


def compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())


def traefik() -> dict:
    """``traefik.yml`` con la plantilla del dominio resuelta, como hace Traefik."""
    text = (ROOT / "compose" / "production" / "traefik" / "traefik.yml").read_text()
    return yaml.safe_load(text.replace('{{ env "URBANCHECK_DOMAIN" }}', DOMAIN))


def route(path: str, host: str = DOMAIN) -> str:
    """El servicio al que Traefik manda ``host`` + ``path`` por HTTPS.

    Gana la regla más larga, que es la prioridad por defecto de Traefik.
    """
    routers = traefik()["http"]["routers"].values()
    candidates = []
    for router in routers:
        if "web-secure" not in router["entryPoints"]:
            continue
        rule = router["rule"]
        hosts = re.findall(r"Host\(`([^`]+)`\)", rule)
        prefixes = re.findall(r"PathPrefix\(`([^`]+)`\)", rule)
        if host in hosts and all(path.startswith(p) for p in prefixes):
            candidates.append((router.get("priority", len(rule)), router["service"]))
    return max(candidates)[1]


class TestPanelInProduction:
    """C-04: el panel es un servicio más del despliegue."""

    def test_the_panel_is_built_from_its_runtime_stage(self):
        panel = compose()["services"]["panel"]

        assert panel["build"]["target"] == "runtime"
        assert panel["environment"]["API_UPSTREAM"] == "http://django:5000"

    def test_the_domain_is_a_variable(self):
        text = (ROOT / "compose" / "production" / "traefik" / "traefik.yml").read_text()

        assert "urbancheck.com.ar" not in text.split("http:", 1)[1]
        traefik_env = compose()["services"]["traefik"]["environment"]
        assert "URBANCHECK_DOMAIN" in traefik_env

    def test_panel_subdomain_goes_to_the_panel(self):
        assert route("/", host=f"panel.{DOMAIN}") == "panel"
        assert route("/reportes", host=f"panel.{DOMAIN}") == "panel"

    def test_the_shared_report_link_goes_to_the_panel(self):
        assert route("/r/0b6f2c1e-0000-4000-8000-000000000000") == "panel"

    def test_media_still_goes_to_nginx(self):
        assert route("/media/reports/foto.jpg") == "django-media"

    def test_everything_else_on_the_domain_goes_to_django(self):
        assert route("/api/reports/") == "django"
        assert route("/.well-known/apple-app-site-association") == "django"
        assert route("/.well-known/assetlinks.json") == "django"

    def test_template_braces_only_appear_in_rules(self):
        """Traefik interpreta la plantilla en todo el archivo, comentarios
        incluidos: unas llaves dobles en un comentario lo dejan sin rutas."""
        text = (ROOT / "compose" / "production" / "traefik" / "traefik.yml").read_text()
        for line in text.splitlines():
            if "{{" in line:
                assert line.strip().startswith("rule:"), line


class TestPanelHsts:
    """C-05: el TLS del panel termina en Traefik, así que el HSTS va ahí."""

    def test_the_panel_routers_send_hsts(self):
        config = traefik()["http"]
        for name in ("panel-router", "panel-share-router"):
            middlewares = config["routers"][name].get("middlewares", [])
            headers = [
                config["middlewares"][m]["headers"]
                for m in middlewares
                if "headers" in config["middlewares"][m]
            ]
            assert any(h.get("stsSeconds", 0) >= 31536000 for h in headers), name  # noqa: PLR2004
