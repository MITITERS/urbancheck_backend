"""Mide la detección de duplicados con un volumen grande (US-026, escenario 9).

Carga ``--reports`` reportes dispersos alrededor de una municipalidad —de todas
las categorías, la mayoría ya cerrados, como un municipio con años de uso—,
corre ``--lookups`` búsquedas en puntos al azar y muestra el promedio, el p95 y
el plan de Postgres de una de ellas.

**No deja nada en la base**: todo corre dentro de una transacción que se
revierte al final, incluidos la municipalidad y el usuario de prueba.
"""

from __future__ import annotations

import random
import statistics
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection
from django.db import transaction
from django.test.utils import CaptureQueriesContext

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.municipalities.models import Municipality
from urbancheck.reports.duplicates import ACTIVE_STATUSES
from urbancheck.reports.duplicates import find_duplicate
from urbancheck.reports.models import Report
from urbancheck.users.models import User

#: Villa María, con un recuadro de unos 10 km de lado.
CENTER = (-32.4106, -63.2436)
SPREAD_DEGREES = 0.05
BATCH = 5000
#: Siete de cada diez reportes de un municipio con historia ya están cerrados.
CLOSED_SHARE = 0.7


class Command(BaseCommand):
    help = (
        "Mide la detección de duplicados sobre muchos reportes de prueba. "
        "Revierte todo al terminar."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reports", type=int, default=50_000)
        parser.add_argument("--lookups", type=int, default=200)
        parser.add_argument("--seed", type=int, default=26)
        parser.add_argument(
            "--report",
            metavar="FILE",
            help="Escribe el informe en FILE.",
        )

    def handle(self, *args, reports, lookups, seed, report=None, **options):
        # Datos de prueba reproducibles, no un uso criptográfico.
        rng = random.Random(seed)  # noqa: S311
        with transaction.atomic():
            text = self._measure(rng, reports, lookups)
            # Nada de lo creado sobrevive a la medición.
            transaction.set_rollback(True)
        self.stdout.write(text)
        if report:
            Path(report).write_text(text, encoding="utf-8")

    def _measure(self, rng: random.Random, count: int, lookups: int) -> str:
        municipality = Municipality.objects.create(
            city="Benchmark",
            province="Córdoba",
            latitude=CENTER[0],
            longitude=CENTER[1],
        )
        author = User.objects.create_user(
            email="benchmark-us026@example.invalid",
            password=None,
        )
        categories = list(Report.Category.values)
        closed = [s for s in Report.Status.values if s not in ACTIVE_STATUSES]
        active = list(ACTIVE_STATUSES)

        started = time.perf_counter()
        for offset in range(0, count, BATCH):
            Report.objects.bulk_create(
                Report(
                    author=author,
                    municipality=municipality,
                    photo_status=PhotoStatus.PROCESADA,
                    description="Reporte de prueba del benchmark.",
                    category=rng.choice(categories),
                    status=rng.choice(
                        closed if rng.random() < CLOSED_SHARE else active,
                    ),
                    latitude=round(CENTER[0] + rng.uniform(-1, 1) * SPREAD_DEGREES, 6),
                    longitude=round(CENTER[1] + rng.uniform(-1, 1) * SPREAD_DEGREES, 6),
                )
                for _ in range(min(BATCH, count - offset))
            )
        load_seconds = time.perf_counter() - started
        with connection.cursor() as cursor:
            cursor.execute(f"ANALYZE {Report._meta.db_table}")  # noqa: SLF001

        times = []
        found = 0
        for _ in range(lookups):
            point = (
                CENTER[0] + rng.uniform(-1, 1) * SPREAD_DEGREES,
                CENTER[1] + rng.uniform(-1, 1) * SPREAD_DEGREES,
            )
            started = time.perf_counter()
            hit = find_duplicate(
                category=rng.choice(categories),
                latitude=point[0],
                longitude=point[1],
                municipality=municipality,
            )
            times.append((time.perf_counter() - started) * 1000)
            found += hit is not None

        plan = self._plan(municipality, categories[0])
        p95 = statistics.quantiles(times, n=20)[-1]
        uses_index = "report_duplicate_lookup" in plan
        lines = [
            "# Detección de duplicados con volumen (US-026, escenario 9)",
            "",
            f"- Reportes cargados: {count} ({CLOSED_SHARE:.0%} cerrados, "
            f"{len(categories)} categorías, recuadro de ~10 km), "
            f"en {load_seconds:.1f} s",
            f"- Búsquedas: {lookups}, con duplicado en {found}",
            f"- Tiempo por búsqueda: promedio {statistics.fmean(times):.2f} ms · "
            f"mediana {statistics.median(times):.2f} ms · p95 {p95:.2f} ms · "
            f"máximo {max(times):.2f} ms",
            "- Usa el índice `report_duplicate_lookup`: "
            f"{'sí' if uses_index else 'NO'}",
            "",
            "## Plan de una búsqueda (EXPLAIN ANALYZE)",
            "",
            "```",
            plan,
            "```",
            "",
            "Todo lo cargado se revirtió al terminar.",
        ]
        return "\n".join(lines) + "\n"

    def _plan(self, municipality, category: str) -> str:
        with CaptureQueriesContext(connection) as queries:
            find_duplicate(
                category=category,
                latitude=CENTER[0],
                longitude=CENTER[1],
                municipality=municipality,
            )
        (query,) = queries.captured_queries
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN ANALYZE {query['sql']}")
            return "\n".join(row[0] for row in cursor.fetchall())
