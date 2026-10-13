"""Benchmark del servicio de anonimización sobre el set de prueba (US-041, escenario 9).

El set vive en ``urbancheck/anonymization/benchmark/``: imágenes urbanas con
licencia libre de Wikimedia Commons y un ``manifest.json`` con, por imagen,
cuántos rostros reconocibles y cuántas patentes legibles tiene. Esos conteos se
etiquetaron a mano mirando cada foto (el criterio está en el README del set).

La tasa es por conteo: en cada imagen se acreditan como detectados hasta tantos
objetos como tiene etiquetados. Una imagen con menos detecciones que etiquetas
aporta falsos negativos y se lista; con ``--annotate`` se dibujan las cajas
para revisar a ojo cuáles son.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import cv2
import numpy as np
from django.core.management.base import BaseCommand
from PIL import Image

from urbancheck.anonymization.service import AnonymizationResult
from urbancheck.anonymization.service import process

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmark"


KINDS = (("faces", "Rostros"), ("plates", "Patentes"))


@dataclass
class Tally:
    """Lo acumulado sobre todo el set."""

    hits: dict[str, int] = field(default_factory=lambda: {"faces": 0, "plates": 0})
    expected: dict[str, int] = field(default_factory=lambda: {"faces": 0, "plates": 0})
    misses: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
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
            line = f"{entry['file']}: {kind} {found[kind]}/{expected}"
            if found[kind] < expected:
                self.misses.append(line)
            elif found[kind] > expected:
                self.extras.append(line)


class Command(BaseCommand):
    help = "Mide la tasa de detección y el tiempo del servicio de anonimización."

    def add_arguments(self, parser):
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

    def handle(self, *args, annotate=None, output=None, **options):
        manifest = json.loads((BENCHMARK_DIR / "manifest.json").read_text())
        for directory in (annotate, output):
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)

        tally = Tally()
        for entry in manifest:
            path = BENCHMARK_DIR / "images" / entry["file"]
            with path.open("rb") as file:
                result = process(file)
            tally.add(entry, result)
            if output:
                Path(output, result.content.name or entry["file"]).write_bytes(
                    result.content.read(),
                )
            if annotate:
                self._annotate(path, result.detections, Path(annotate, entry["file"]))

        self.stdout.write(f"Imágenes: {len(manifest)}")
        self._report(tally)

    def _report(self, tally: Tally) -> None:
        for kind, label in KINDS:
            hit, expected = tally.hits[kind], tally.expected[kind]
            self.stdout.write(f"{label}: {hit}/{expected} ({_rate(hit, expected)})")
        hit, expected = sum(tally.hits.values()), sum(tally.expected.values())
        self.stdout.write(f"Total: {hit}/{expected} ({_rate(hit, expected)})")

        times = tally.times
        p95 = statistics.quantiles(times, n=20)[-1] if len(times) > 1 else times[0]
        self.stdout.write(
            f"Tiempo por imagen: mediana {statistics.median(times):.0f} ms, "
            f"p95 {p95:.0f} ms, máximo {max(times):.0f} ms",
        )
        self.stdout.write("\nFalsos negativos (detectados/esperados):")
        for line in tally.misses or ["ninguno"]:
            self.stdout.write(f"  {line}")
        self.stdout.write(
            "\nDetecciones de más, posibles falsos positivos (detectados/esperados):",
        )
        for line in tally.extras or ["ninguna"]:
            self.stdout.write(f"  {line}")

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


def _rate(hit: int, expected: int) -> str:
    return f"{hit / expected:.1%}" if expected else "sin etiquetas"
