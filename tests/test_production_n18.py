"""N-18: los contenedores expuestos de producción no corren como root.

- El nginx de ``/media/`` usa la imagen sin privilegios y escucha en 8080.
- Traefik corre con un usuario común y solo la capacidad ``NET_BIND_SERVICE``,
  que le deja abrir el 80 y el 443.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "compose" / "production"


def services() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())[
        "services"
    ]


def traefik_services() -> dict:
    text = (PRODUCTION / "traefik" / "traefik.yml").read_text()
    config = yaml.safe_load(text.replace('{{ env "URBANCHECK_DOMAIN" }}', "x.test"))
    return {
        name: service["loadBalancer"]["servers"][0]["url"]
        for name, service in config["http"]["services"].items()
    }


class TestMediaNginx:
    def test_it_uses_the_unprivileged_image(self):
        dockerfile = (PRODUCTION / "nginx" / "Dockerfile").read_text()

        assert re.search(
            r"^FROM docker\.io/nginxinc/nginx-unprivileged:\d+\.\d+\.\d+-alpine$",
            dockerfile,
            re.MULTILINE,
        )

    def test_it_listens_on_8080_and_traefik_points_there(self):
        conf = (PRODUCTION / "nginx" / "default.conf").read_text()

        assert re.search(r"^\s*listen\s+8080;", conf, re.MULTILINE)
        assert traefik_services()["django-media"] == "http://nginx:8080"

    def test_traefik_points_to_the_unprivileged_panel(self):
        assert traefik_services()["panel"] == "http://panel:8080"


class TestTraefik:
    def test_it_runs_as_a_regular_user_with_only_net_bind_service(self):
        traefik = services()["traefik"]

        user = str(traefik["user"]).split(":")[0]
        assert user not in {"0", "root"}
        assert traefik["cap_drop"] == ["ALL"]
        assert traefik["cap_add"] == ["NET_BIND_SERVICE"]
        assert "no-new-privileges:true" not in traefik.get("security_opt", [])

    def test_the_binary_carries_the_capability(self):
        dockerfile = (PRODUCTION / "traefik" / "Dockerfile").read_text()

        assert "setcap cap_net_bind_service=+ep" in dockerfile
        assert "chown" in dockerfile
