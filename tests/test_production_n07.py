"""N-07: la base y Redis de producción sin credenciales de más.

- PostgreSQL: Django entra con un rol de aplicación sin superusuario, dueño de
  la base. Lo crea un script de inicialización que se monta **solo** en el
  compose de producción: el de desarrollo usa la misma imagen y no cambia.
- Redis: pide contraseña (``requirepass``).
"""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INIT_DIR = "./compose/production/postgres/init"
INIT_SCRIPT = ROOT / "compose" / "production" / "postgres" / "init" / "10-app-role.sh"
ENTRYPOINT = ROOT / "compose" / "production" / "django" / "entrypoint"


def services(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())["services"]


class TestPostgresAppRole:
    def test_production_mounts_the_init_script(self):
        volumes = services("docker-compose.production.yml")["postgres"]["volumes"]

        assert f"{INIT_DIR}:/docker-entrypoint-initdb.d:ro" in volumes

    def test_the_local_stack_does_not(self):
        volumes = services("docker-compose.local.yml")["postgres"]["volumes"]

        assert not any("docker-entrypoint-initdb.d" in volume for volume in volumes)

    def test_the_role_is_not_a_superuser_and_owns_the_database(self):
        script = INIT_SCRIPT.read_text()

        assert "NOSUPERUSER" in script
        assert "NOCREATEROLE" in script
        assert "NOCREATEDB" in script
        assert "OWNER TO" in script
        assert os.access(INIT_SCRIPT, os.X_OK)

    def test_django_connects_with_the_app_role(self, tmp_path):
        """El entrypoint arma DATABASE_URL con el rol de aplicación si existe."""
        fake = tmp_path / "wait-for-it"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        env = {
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "urbancheck",
            "POSTGRES_USER": "admin",
            "POSTGRES_PASSWORD": "clave-admin",
            "POSTGRES_APP_USER": "urbancheck_app",
            "POSTGRES_APP_PASSWORD": "clave-app",
        }

        result = subprocess.run(  # noqa: S603
            ["/bin/bash", str(ENTRYPOINT), "printenv", "DATABASE_URL"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        assert result.stdout.strip() == (
            "postgres://urbancheck_app:clave-app@postgres:5432/urbancheck"
        )

    def test_without_an_app_role_nothing_changes(self, tmp_path):
        """El compose local no define el rol: sigue con el usuario de siempre."""
        fake = tmp_path / "wait-for-it"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        env = {
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "urbancheck",
            "POSTGRES_USER": "admin",
            "POSTGRES_PASSWORD": "clave-admin",
        }

        result = subprocess.run(  # noqa: S603
            ["/bin/bash", str(ENTRYPOINT), "printenv", "DATABASE_URL"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        assert result.stdout.strip() == (
            "postgres://admin:clave-admin@postgres:5432/urbancheck"
        )


class TestRedisPassword:
    def test_production_redis_requires_a_password(self):
        redis = services("docker-compose.production.yml")["redis"]

        assert "./.envs/.production/.redis" in redis["env_file"]
        assert "requirepass" in " ".join(redis["command"])

    def test_the_local_redis_is_unchanged(self):
        redis = services("docker-compose.local.yml")["redis"]

        assert "command" not in redis

    def test_the_env_example_documents_it(self):
        lines = (ROOT / ".env.example").read_text().splitlines()

        assert "REDIS_PASSWORD=" in lines
        assert any(
            line.startswith("REDIS_URL=redis://:") and "@redis:6379/0" in line
            for line in lines
        )
