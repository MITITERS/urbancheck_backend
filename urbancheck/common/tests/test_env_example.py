"""``.env.example`` completo (Sprint 5, regla 7 y SEC-19).

Toda variable que lea la configuración o el código tiene que figurar en
``.env.example`` con su valor por defecto. El test lee el código fuente en vez
de una lista a mano: una variable nueva que nadie documentó lo hace fallar.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: ``env("X", ...)``, ``env.int("X", ...)`` y demás, aunque la llamada ocupe
#: varias líneas.
ENV_CALL = re.compile(r'\benv(?:\.(?:int|bool|list|str|db))?\(\s*"([A-Z0-9_]+)"')


def variables_read_by_the_code() -> set[str]:
    sources = [
        *ROOT.glob("config/**/*.py"),
        *(
            path
            for path in ROOT.glob("urbancheck/**/*.py")
            if "tests" not in path.parts and "migrations" not in path.parts
        ),
    ]
    found: set[str] = set()
    for path in sources:
        found.update(ENV_CALL.findall(path.read_text(encoding="utf-8")))
    return found


def variables_documented() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z0-9_]+)=", text, flags=re.MULTILINE))


def test_every_variable_the_code_reads_is_documented():
    """CP-SEC19-01: ninguna variable sin documentar en ``.env.example``."""
    missing = variables_read_by_the_code() - variables_documented()

    assert not missing, sorted(missing)


def test_the_example_carries_no_secret():
    """CP-SEC19-02: las variables secretas van vacías en el ejemplo."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    secrets = {
        "DJANGO_SECRET_KEY",
        "DJANGO_RESOLUTION_COMPARISON_API_KEY",
        "POSTGRES_PASSWORD",
        "CELERY_FLOWER_PASSWORD",
        "DATABASE_URL",
    }
    for name in secrets:
        assert re.search(rf"^{name}=$", text, flags=re.MULTILINE), name
