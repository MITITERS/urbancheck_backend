"""N-12: el CI del backend arranca y no hereda dependencias con CVE conocidas.

``astral-sh/setup-uv`` dejó de publicar la etiqueta flotante de la versión
mayor (``@v10`` no existe), así que se fija el commit de una versión concreta.
"""

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# Primera versión sin avisos de pip-audit (sección 9 del documento de seguridad).
MINIMUM_VERSIONS = {
    "pillow": (13, 0, 0),
    "virtualenv": (21, 14, 9),
}


def _steps():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    for job in workflow["jobs"].values():
        yield from job["steps"]


def test_setup_uv_is_pinned_to_a_commit():
    refs = [
        step["uses"].split("@", 1)[1]
        for step in _steps()
        if step.get("uses", "").startswith("astral-sh/setup-uv@")
    ]

    assert refs
    for ref in refs:
        assert FULL_SHA.match(ref), ref


def test_lock_has_no_known_vulnerable_versions():
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {pkg["name"]: pkg["version"] for pkg in lock["package"]}

    for name, minimum in MINIMUM_VERSIONS.items():
        version = tuple(int(part) for part in locked[name].split(".")[:3])
        assert version >= minimum, f"{name} {locked[name]}"
