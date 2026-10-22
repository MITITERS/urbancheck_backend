"""Benchmark del servicio de anonimización (US-041, escenarios 8 y 9).

Lee un set de imágenes de una carpeta **no versionada** —por defecto
``ANONYMIZATION_REFERENCE_SET``— con esta forma::

    <carpeta>/
      manifest.json       # [{"file": "...", "faces": N, "plates": M}, ...]
      images/<file>       # una entrada del manifiesto por imagen

Los conteos de ``faces`` y ``plates`` se etiquetan a mano mirando cada foto (el
criterio está en ``urbancheck/anonymization/benchmark/README.md``). Las fotos
son de personas y de la vía pública: nunca se suben al repositorio ni a la
imagen de Docker.

La tasa es por conteo: en cada imagen se acreditan como detectados hasta tantos
objetos como tiene etiquetados. Una imagen con menos detecciones que etiquetas
aporta falsos negativos y se lista con su nombre y el tipo; con ``--annotate``
se dibujan las cajas para revisar a ojo cuáles son. Con ``--report`` el
resultado queda además en un archivo Markdown.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone
from PIL import Image

from urbancheck.anonymization.service import AnonymizationResult
from urbancheck.anonymization.service import process

KINDS = (("faces", "Rostros"), ("plates", "Patentes"))
LABELS = dict(KINDS)


@dataclass
class Tally:
    """Lo acumulado sobre todo el set."""

    hits: dict[str, int] = field(default_factory=lambda: {"faces": 0, "plates": 0})
    expected: dict[str, int] = field(default_factory=lambda: {"faces": 0, "plates": 0})
    #: (archivo, tipo, detectados, esperados)
    misses: list[tuple[str, str, int, int]] = field(default_factory=list)
    extras: list[tuple[str, str, int, int]] = field(default_factory=list)
    times: list[float] = field(default_factory=list)

    def add(self, entry: dict, result: AnonymizationResult) -> None:
        self.times.append(result.elapsed_ms)
        found = {
            "faces": len(result.detections.faces),
            "plates": len(result.detections.plates),
        }
        for kind, _ in KINDS:
            expected = entry[kind]
            self.hits[kind] += min(found[kind], expected)
            self.expected[kind] += expected
            row = (entry["file"], kind, found[kind], expected)
            if found[kind] < expected:
                self.misses.append(row)
            elif found[kind] > expected:
                self.extras.append(row)

    def timing(self) -> dict[str, float]:
        times = self.times
        p95 = statistics.quantiles(times, n=20)[-1] if len(times) > 1 else times[0]
        return {
            "mean": statistics.fmean(times),
            "median": statistics.median(times),
            "p95": p95,
            "max": max(times),
        }


class Command(BaseCommand):
    help = (
        "Mide la tasa de detección y el tiempo del servicio de anonimización "
        "sobre un set no versionado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "folder",
            nargs="?",
            help="Carpeta con manifest.json e images/. Por defecto, "
            "ANONYMIZATION_REFERENCE_SET.",
        )
        parser.add_argument(
            "--report",
            metavar="FILE",
            help="Escribe el informe en FILE (Markdown).",
        )
        parser.add_argument(
            "--annotate",
            metavar="DIR",
            help="Escribe en DIR cada imagen con las cajas detectadas "
            "(rostros en verde, patentes en rojo).",
        )
        parser.add_argument(
            "--output",
            metavar="DIR",
            help="Escribe en DIR la versión anonimizada de cada imagen.",
        )

    def handle(
        self, *args, folder=None, report=None, annotate=None, output=None, **options,
    ):
        root = Path(folder or settings.ANONYMIZATION_REFERENCE_SET)
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            msg = (
                f"No hay set de referencia en {root}: falta manifest.json. El "
                "equipo tiene que dejar ahí las imágenes y sus etiquetas (ver "
                "urbancheck/anonymization/benchmark/README.md)."
            )
            raise CommandError(msg)
        manifest = json.loads(manifest_path.read_text())
        for directory in (annotate, output):
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)

        tally = Tally()
        for entry in manifest:
            path = root / "images" / entry["file"]
            if not path.exists():
                msg = (
                    f"El manifiesto nombra {entry['file']}, que no está en "
                    f"{root / 'images'}."
                )
                raise CommandError(msg)
            with path.open("rb") as file:
                result = process(file)
            tally.add(entry, result)
            if output:
                Path(output, result.content.name or entry["file"]).write_bytes(
                    result.content.read(),
                )
            if annotate:
                self._annotate(path, result.detections, Path(annotate, entry["file"]))

        text = render_report(root, len(manifest), tally)
        self.stdout.write(text)
        if report:
            Path(report).write_text(text, encoding="utf-8")

    def _annotate(self, source: Path, detections, target: Path) -> None:
        pixels = np.asarray(Image.open(source).convert("RGB"))
        canvas = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        for color, boxes in (
            ((0, 200, 0), detections.faces),
            ((0, 0, 255), detections.plates),
        ):
            for index, box in enumerate(boxes, 1):
                cv2.rectangle(
                    canvas,
                    (box.x, box.y),
                    (box.x + box.w, box.y + box.h),
                    color,
                    2,
                )
                cv2.putText(
                    canvas,
                    str(index),
                    (box.x, max(12, box.y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                )
        cv2.imwrite(str(target), canvas)


def render_report(root: Path, count: int, tally: Tally) -> str:
    """El informe en Markdown: tasas, tiempos, falsos negativos y máquina."""
    lines = [
        "# Benchmark de anonimización (US-041)",
        "",
        f"- Fecha: {timezone.localtime():%Y-%m-%d %H:%M}",
        f"- Set: `{root.name}` ({count} imágenes)",
        f"- Máquina: {platform.machine()}, {os.cpu_count()} CPU, "
        f"{_memory()}, Python {platform.python_version()}",
        "",
        "## Tasa de detección",
        "",
        "| Tipo | Detectados | Etiquetados | Tasa |",
        "| --- | --- | --- | --- |",
    ]
    for kind, label in KINDS:
        hit, expected = tally.hits[kind], tally.expected[kind]
        lines.append(f"| {label} | {hit} | {expected} | {_rate(hit, expected)} |")
    hit, expected = sum(tally.hits.values()), sum(tally.expected.values())
    lines.append(f"| Total | {hit} | {expected} | {_rate(hit, expected)} |")

    timing = tally.timing()
    lines += [
        "",
        "## Tiempo por imagen",
        "",
        f"Promedio {timing['mean']:.0f} ms · mediana {timing['median']:.0f} ms · "
        f"p95 {timing['p95']:.0f} ms · máximo {timing['max']:.0f} ms",
        "",
        "## Falsos negativos",
        "",
    ]
    lines += _rows(tally.misses, "Ninguno.")
    lines += ["", "## Detecciones de más (posibles falsos positivos)", ""]
    lines += _rows(tally.extras, "Ninguna.")
    return "\n".join(lines) + "\n"


def _rows(rows, empty: str) -> list[str]:
    if not rows:
        return [empty]
    out = ["| Archivo | Tipo | Detectados | Etiquetados |", "| --- | --- | --- | --- |"]
    out += [
        f"| {name} | {LABELS[kind]} | {found} | {expected} |"
        for name, kind, found, expected in rows
    ]
    return out


def _memory() -> str:
    try:
        pages = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except ValueError, OSError, AttributeError:
        return "RAM sin dato"
    return f"{pages / 1024**3:.1f} GB de RAM"


def _rate(hit: int, expected: int) -> str:
    return f"{hit / expected:.1%}" if expected else "sin etiquetas"
