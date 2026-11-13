"""Términos y condiciones y política de privacidad, desde archivos (RN-10, C-23).

Los textos viven en el repositorio, no en la base: ``LEGAL_DOCUMENTS_DIR``
tiene un ``versiones.toml`` con una entrada por versión publicada y, por cada
una, una carpeta con ``terminos.md`` y ``privacidad.md``. Los dos documentos
comparten número de versión y se aceptan juntos; en el usuario se guarda esa
versión y la fecha (``terms_version`` y ``terms_accepted_at``).

Publicar una versión nueva es agregar su carpeta y su entrada, y reiniciar. Una
versión ya aceptada por alguien no se edita: se publica otra, porque la
aceptación guardada apunta a la versión por su número.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

REGISTRY_FILE = "versiones.toml"
TERMS_FILE = "terminos.md"
PRIVACY_FILE = "privacidad.md"


@dataclass(frozen=True)
class LegalDocuments:
    """Una versión publicada de los dos documentos."""

    version: str
    published_at: datetime
    terms: str
    privacy: str


def current_legal_documents() -> LegalDocuments | None:
    """La versión vigente: la última ya publicada, o ninguna.

    La fecha se evalúa en cada llamada, así que una versión cargada con fecha
    futura entra en vigencia sola, sin reiniciar.
    """
    now = timezone.now()
    published = [
        v for v in _load(str(settings.LEGAL_DOCUMENTS_DIR)) if v.published_at <= now
    ]
    return max(published, key=lambda v: v.published_at, default=None)


@lru_cache
def _load(directory: str) -> tuple[LegalDocuments, ...]:
    """Lee el registro y los textos. Falla fuerte ante un archivo que falta.

    Se cachea por carpeta: los archivos no cambian sin reiniciar el proceso, y
    leerlos en cada pedido sería trabajo repetido en cada respuesta de ``/me``.
    """
    root = Path(directory)
    registry = root / REGISTRY_FILE
    if not registry.exists():
        return ()
    with registry.open("rb") as fh:
        entries = tomllib.load(fh).get("version", [])

    versions = []
    seen = set()
    for entry in entries:
        number = str(entry["numero"])
        published_at = entry["vigente_desde"]
        if number in seen:
            msg = f"La versión {number} aparece dos veces en {registry}."
            raise ImproperlyConfigured(msg)
        if not isinstance(published_at, datetime) or published_at.tzinfo is None:
            msg = (
                f"vigente_desde de la versión {number} tiene que ser fecha y hora "
                "con zona horaria, por ejemplo 2026-10-30T00:00:00-03:00."
            )
            raise ImproperlyConfigured(msg)
        seen.add(number)
        folder = root / number
        versions.append(
            LegalDocuments(
                version=number,
                published_at=published_at,
                terms=_read(folder / TERMS_FILE),
                privacy=_read(folder / PRIVACY_FILE),
            ),
        )
    return tuple(versions)


def _read(path: Path) -> str:
    if not path.exists():
        msg = f"Falta {path}: cada versión publicada lleva sus dos documentos."
        raise ImproperlyConfigured(msg)
    return path.read_text(encoding="utf-8")
