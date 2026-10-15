"""US-026 — detección automática de reportes duplicados.

Prueban el servicio de dominio solo, sin pasar por la creación: qué se hace con
el resultado es de US-032 y está en ``test_duplicate_reports.py``.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.municipalities.tests.factories import square_boundary
from urbancheck.reports import duplicates
from urbancheck.reports.duplicates import find_duplicate
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory

pytestmark = pytest.mark.django_db

HERE = (-32.410300, -63.240000)
#: ~5 m al norte de ``HERE``.
FIVE_METERS = (-32.410255, -63.240000)
#: ~20 m al norte de ``HERE``: dentro del radio por defecto.
TWENTY_METERS = (-32.410120, -63.240000)
#: ~40 m al norte de ``HERE``: fuera de 30 m, dentro de los 50 m de US-032.
FORTY_METERS = (-32.409940, -63.240000)

CLOSED_STATUSES = (
    Report.Status.RESUELTO,
    Report.Status.CANCELADO,
    Report.Status.ARCHIVADO,
)


def existing_at(point, municipality, **extra):
    latitude, longitude = point
    return ReportFactory.create(
        municipality=municipality,
        category=extra.pop("category", Report.Category.BACHE),
        status=extra.pop("status", Report.Status.REPORTADO),
        latitude=latitude,
        longitude=longitude,
        **extra,
    )


def look(municipality, category=Report.Category.BACHE, point=HERE):
    latitude, longitude = point
    return find_duplicate(
        category=category,
        latitude=latitude,
        longitude=longitude,
        municipality=municipality,
    )


def test_the_default_radius_is_30_meters(settings):
    """El valor que pide la historia, sin pisarlo desde el entorno del test."""
    assert settings.DUPLICATE_REPORT_RADIUS_METERS == 30  # noqa: PLR2004


def test_same_category_within_the_radius(active_municipality):
    """Escenario 1."""
    existing = existing_at(TWENTY_METERS, active_municipality)

    duplicate = look(active_municipality)

    assert duplicate == existing
    assert 15 <= duplicate.distance_meters <= 25  # noqa: PLR2004


def test_same_place_another_category(active_municipality):
    """Escenario 2: un bache y una vereda rota a 5 m son dos problemas."""
    existing_at(FIVE_METERS, active_municipality, category=Report.Category.BACHE)

    assert look(active_municipality, category=Report.Category.VEREDA) is None


def test_same_category_outside_the_radius(active_municipality):
    """Escenario 3: a ~40 m no bloquea con el radio por defecto."""
    existing_at(FORTY_METERS, active_municipality)

    assert look(active_municipality) is None


@pytest.mark.parametrize("status", duplicates.ACTIVE_STATUSES)
def test_every_active_status_counts(active_municipality, status):
    existing = existing_at(FIVE_METERS, active_municipality, status=status)

    assert look(active_municipality) == existing


@pytest.mark.parametrize("status", CLOSED_STATUSES)
def test_a_closed_report_does_not_count(active_municipality, status):
    """Escenario 4: un problema que reaparece después del cierre es nuevo."""
    existing_at(FIVE_METERS, active_municipality, status=status)

    assert look(active_municipality) is None


def test_every_status_is_either_active_or_closed():
    """Un estado nuevo tiene que decidir de qué lado cae."""
    assert set(duplicates.ACTIVE_STATUSES) | set(CLOSED_STATUSES) == set(
        Report.Status,
    )


def test_the_closest_one_wins(active_municipality):
    """Escenario 5."""
    existing_at(TWENTY_METERS, active_municipality)
    closest = existing_at(FIVE_METERS, active_municipality)

    assert look(active_municipality) == closest


def test_another_municipality_does_not_count(active_municipality):
    """Escenario 7: la deduplicación no cruza un límite jurisdiccional."""
    neighbour = MunicipalityFactory.create(boundary=square_boundary(10, 10, 1))
    existing_at(FIVE_METERS, neighbour)

    assert look(active_municipality) is None


def test_the_radius_is_read_from_configuration(active_municipality, settings):
    """Escenario 6: el valor vigente se aplica sin tocar código."""
    existing = existing_at(FORTY_METERS, active_municipality)
    assert look(active_municipality) is None

    settings.DUPLICATE_REPORT_RADIUS_METERS = 50

    assert look(active_municipality) == existing


def test_the_lookup_uses_the_index(active_municipality):
    """Escenario 9: la consulta la resuelve el índice, no un recorrido completo.

    La tabla se llena como la de un municipio con historia —muchos reportes
    cerrados y de otras categorías, dispersos— y se le pasa ``ANALYZE``. Sin
    eso, qué plan elige Postgres depende de las estadísticas que dejaron los
    tests anteriores: con la tabla casi vacía cualquier índice sobre
    ``municipality`` le da lo mismo. El recorrido secuencial se desactiva
    además para que el tamaño chico no lo tiente.
    """
    template = ReportFactory.create(municipality=active_municipality)
    Report.objects.bulk_create(
        Report(
            author=template.author,
            municipality=active_municipality,
            photo=template.photo.name,
            photo_status=PhotoStatus.PROCESADA,
            description="Relleno.",
            category=category,
            status=status,
            latitude=HERE[0] + (offset % 40) * 0.001,
            longitude=HERE[1] + (offset // 40) * 0.001,
        )
        for offset in range(400)
        for category, status in [
            (Report.Category.BACHE, Report.Status.RESUELTO),
            (Report.Category.ALUMBRADO, Report.Status.REPORTADO),
        ]
    )
    existing_at(FIVE_METERS, active_municipality)
    with CaptureQueriesContext(connection) as queries:
        look(active_municipality)
    (query,) = queries.captured_queries

    with connection.cursor() as cursor:
        cursor.execute(f"ANALYZE {Report._meta.db_table}")  # noqa: SLF001
        cursor.execute("SET enable_seqscan = off")
        try:
            cursor.execute(f"EXPLAIN {query['sql']}")
            plan = "\n".join(row[0] for row in cursor.fetchall())
        finally:
            cursor.execute("RESET enable_seqscan")

    assert "report_duplicate_lookup" in plan, plan


def test_the_index_covers_exactly_the_active_statuses():
    """La condición del índice repite la lista; no pueden separarse."""
    (index,) = [
        index
        for index in Report._meta.indexes  # noqa: SLF001
        if index.name == "report_duplicate_lookup"
    ]
    ((lookup, statuses),) = index.condition.children

    assert lookup == "status__in"
    assert set(statuses) == set(duplicates.ACTIVE_STATUSES)
