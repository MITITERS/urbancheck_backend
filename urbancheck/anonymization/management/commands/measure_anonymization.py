"""Tiempo, CPU y memoria del difuminado (US-041, escenario 8).

Procesa ``--runs`` fotos sintéticas de 12 MP —el tamaño de una foto de celular
actual— y, si está, el set de referencia de ``ANONYMIZATION_REFERENCE_SET``.
Informa promedio y p95 de reloj, CPU por imagen y el pico de memoria del
proceso. Llama a ``service.process``, lo mismo que la tarea de Celery.

No toca la base ni el disco: todo pasa en memoria.
"""

from __future__ import annotations

import io
import os
import resource
import statistics
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from urbancheck.anonymization.service import process
from urbancheck.anonymization.tests.images import synthetic_photo

TWELVE_MEGAPIXELS = (4000, 3000)


def _peak_rss_mb() -> float:
    # En Linux ``ru_maxrss`` viene en KiB.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _named(data: bytes) -> io.BytesIO:
    file = io.BytesIO(data)
    file.name = "foto.jpg"
    return file


def _timed(files) -> dict[str, float]:
    wall, cpu = [], []
    for file in files:
        cpu_before, started = _cpu_seconds(), time.perf_counter()
        process(file)
        wall.append((time.perf_counter() - started) * 1000)
        cpu.append((_cpu_seconds() - cpu_before) * 1000)
    p95 = statistics.quantiles(wall, n=20)[-1] if len(wall) > 1 else wall[0]
    return {
        "count": len(wall),
        "mean": statistics.fmean(wall),
        "p95": p95,
        "cpu": statistics.fmean(cpu),
    }


class Command(BaseCommand):
    help = "Mide tiempo, CPU y memoria del difuminado sobre fotos de 12 MP."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=10)

    def handle(self, *args, runs, **options):
        at_start = _peak_rss_mb()
        process(_named(synthetic_photo((320, 240))))
        with_models = _peak_rss_mb()

        photo = synthetic_photo(TWELVE_MEGAPIXELS)
        rows = [
            ("Foto de 12 MP (sintética)", _timed(_named(photo) for _ in range(runs))),
        ]

        images = Path(settings.ANONYMIZATION_REFERENCE_SET) / "images"
        paths = sorted(images.glob("*.jpg")) if images.exists() else []
        if paths:
            rows.append(
                ("Set de referencia", _timed(path.open("rb") for path in paths)),
            )

        self.stdout.write(f"CPU disponibles: {os.cpu_count()}")
        for label, row in rows:
            self.stdout.write(
                f"{label}: {row['count']} imágenes · promedio {row['mean']:.0f} ms · "
                f"p95 {row['p95']:.0f} ms · CPU {row['cpu']:.0f} ms por imagen",
            )
        self.stdout.write(
            f"Memoria (RSS): al arrancar {at_start:.0f} MB · con los modelos "
            f"{with_models:.0f} MB · pico {_peak_rss_mb():.0f} MB",
        )
