"""US-023 — distribución de reportes por categoría y por estado."""

from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import time
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.statistics import FUTURE_DATE_MESSAGE
from urbancheck.reports.statistics import START_AFTER_END_MESSAGE
from urbancheck.reports.statistics import Window
from urbancheck.reports.statistics import distributions
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403

URL = "/api/panel/statistics/"
TODAY = date(2026, 10, 20)
ZONE = ZoneInfo(settings.TIME_ZONE)

Status = Report.Status
Category = Report.Category


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr("urbancheck.reports.statistics.today", lambda: TODAY)


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def created_on(report, day: date, hour: int = 12) -> Report:
    """``created_at`` es ``auto_now_add``: se corrige después de crear."""
    moment = datetime.combine(day, time(hour), tzinfo=ZONE)
    Report.objects.filter(pk=report.pk).update(created_at=moment)
    return report


def report_on(municipality, day: date, **kwargs) -> Report:
    return created_on(ReportFactory.create(municipality=municipality, **kwargs), day)


def bucket(rows: list[dict], key: str) -> dict:
    return next(row for row in rows if row["key"] == key)


@pytest.fixture
def agent():
    return MunicipalAgentFactory.create()


@pytest.fixture
def municipality(agent):
    return agent.municipality


class TestDistributions:
    def test_by_category_with_count_and_percentage(self, agent, municipality):
        """CP-023-01 (US-023 E1)."""
        for _ in range(3):
            report_on(municipality, TODAY, category=Category.BACHE)
        report_on(municipality, TODAY, category=Category.ALUMBRADO)

        data = client_for(agent).get(URL).data

        assert data["total"] == 4  # noqa: PLR2004
        bache = bucket(data["by_category"], Category.BACHE)
        assert bache["count"] == 3  # noqa: PLR2004
        assert bache["percentage"] == 75.0  # noqa: PLR2004
        assert bache["label"] == "Bache"
        assert bucket(data["by_category"], Category.ALUMBRADO)["percentage"] == 25.0  # noqa: PLR2004

    def test_by_status_lists_the_seven_states(self, agent, municipality):
        """CP-023-02 (US-023 E2). Incluidos los que US-012 no muestra."""
        report_on(municipality, TODAY, status=Status.ARCHIVADO)
        report_on(municipality, TODAY, status=Status.CANCELADO)

        rows = client_for(agent).get(URL).data["by_status"]

        assert [row["key"] for row in rows] == list(Status.values)
        assert bucket(rows, Status.ARCHIVADO)["count"] == 1
        assert bucket(rows, Status.CANCELADO)["count"] == 1

    def test_empty_buckets_come_back_in_zero(self, agent, municipality):
        """CP-023-03. El gráfico no cambia de forma entre períodos."""
        report_on(municipality, TODAY, category=Category.BACHE)

        rows = client_for(agent).get(URL).data["by_category"]

        assert len(rows) == len(Category.values)
        assert bucket(rows, Category.SEMAFORO) == {
            "key": Category.SEMAFORO,
            "label": "Semáforo",
            "count": 0,
            "percentage": 0.0,
        }


class TestPeriods:
    def test_default_is_the_last_30_days(self, agent, municipality):
        """CP-023-04 (US-023 E5). Y la respuesta dice qué ventana es."""
        report_on(municipality, date(2026, 9, 21))  # día 30, adentro
        report_on(municipality, date(2026, 9, 20))  # día 31, afuera

        data = client_for(agent).get(URL).data

        assert data["period"] == {
            "key": "30d",
            "start": "2026-09-21",
            "end": "2026-10-20",
        }
        assert data["total"] == 1

    @pytest.mark.parametrize(
        ("period", "start"),
        [("7d", "2026-10-14"), ("30d", "2026-09-21"), ("12m", "2025-10-21")],
    )
    def test_the_available_windows(self, agent, period, start):
        """CP-023-05 (US-023 E4)."""
        data = client_for(agent).get(URL, {"period": period}).data

        assert data["period"]["start"] == start
        assert data["period"]["end"] == "2026-10-20"

    def test_a_custom_range_counts_only_what_was_created_in_it(
        self,
        agent,
        municipality,
    ):
        """CP-023-06 (US-023 E3). Los dos extremos incluidos."""
        report_on(municipality, date(2026, 5, 1))
        report_on(municipality, date(2026, 5, 31))
        report_on(municipality, date(2026, 6, 1))
        report_on(municipality, date(2026, 4, 30))

        data = (
            client_for(agent)
            .get(URL, {"period": "custom", "start": "2026-05-01", "end": "2026-05-31"})
            .data
        )

        assert data["total"] == 2  # noqa: PLR2004

    def test_the_last_day_counts_until_midnight_local_time(self, agent, municipality):
        """CP-023-07. A las 23 de Córdoba ya es el día siguiente en UTC."""
        created_on(
            ReportFactory.create(municipality=municipality),
            date(2026, 5, 31),
            hour=23,
        )

        data = (
            client_for(agent)
            .get(URL, {"period": "custom", "start": "2026-05-01", "end": "2026-05-31"})
            .data
        )

        assert data["total"] == 1

    @pytest.mark.parametrize(
        ("params", "field", "message"),
        [
            (
                {"period": "custom", "start": "2026-06-10", "end": "2026-06-01"},
                "start",
                START_AFTER_END_MESSAGE,
            ),
            (
                {"period": "custom", "start": "2026-10-01", "end": "2026-10-25"},
                "end",
                FUTURE_DATE_MESSAGE,
            ),
            ({"period": "custom", "start": "2026-06-01"}, "end", None),
            ({"period": "semestre"}, "period", None),
        ],
        ids=["invertido", "futuro", "incompleto", "desconocido"],
    )
    def test_an_invalid_range_is_rejected_with_the_reason(
        self,
        agent,
        params,
        field,
        message,
    ):
        """CP-023-08 (US-023 E6). Validado en el backend, no solo en el formulario."""
        response = client_for(agent).get(URL, params)

        assert response.status_code == HTTP_BAD_REQUEST
        assert field in response.data
        if message:
            assert response.data[field] == [message]

    def test_an_empty_period_has_no_percentages(self, agent, municipality):
        """CP-023-09 (US-023 E7). Nada calculado sobre un total nulo."""
        report_on(municipality, date(2025, 1, 1))

        data = client_for(agent).get(URL).data

        assert data["total"] == 0
        assert all(row["percentage"] is None for row in data["by_category"])
        assert all(row["percentage"] is None for row in data["by_status"])


class TestJurisdiction:
    def test_another_municipality_never_counts(self, agent, municipality):
        """CP-023-10 (US-023 E8)."""
        report_on(municipality, TODAY)
        foreign = ReportFactory.create()
        created_on(foreign, TODAY)

        data = client_for(agent).get(URL).data

        assert data["total"] == 1

    def test_no_parameter_can_widen_it(self, agent, municipality):
        """CP-023-11 (US-023 E8). Sin importar lo que mande el cliente."""
        foreign = created_on(ReportFactory.create(), TODAY)

        data = (
            client_for(agent).get(URL, {"municipality": foreign.municipality_id}).data
        )

        assert data["total"] == 0

    def test_the_admin_sees_one_municipality_from_its_page(self, municipality):
        """CP-023-12 (US-023 E9). La misma vista y los mismos filtros."""
        report_on(municipality, TODAY, category=Category.BACHE)
        created_on(ReportFactory.create(), TODAY)
        admin = PlatformAdminFactory.create()

        response = client_for(admin).get(
            f"/api/municipalities/{municipality.pk}/statistics/",
            {"period": "7d"},
        )

        assert response.status_code == HTTP_OK
        assert response.data["total"] == 1
        assert response.data["period"]["key"] == "7d"

    def test_the_admin_has_no_global_panel_statistics(self):
        """CP-023-13. El admin entra por la ficha, como a los reportes."""
        admin = PlatformAdminFactory.create()

        assert client_for(admin).get(URL).status_code == HTTP_FORBIDDEN

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, OperatorFactory],
        ids=["ciudadano", "validador", "operario"],
    )
    def test_other_roles_get_a_403(self, factory, municipality):
        """CP-023-14 (US-023 E10)."""
        user = factory.create()

        assert client_for(user).get(URL).status_code == HTTP_FORBIDDEN
        assert (
            client_for(user)
            .get(f"/api/municipalities/{municipality.pk}/statistics/")
            .status_code
            == HTTP_FORBIDDEN
        )


def test_the_aggregation_runs_in_the_database(municipality, django_assert_num_queries):
    """CP-023-15 (US-023 DoD). Tres consultas, tenga los reportes que tenga."""
    for category in (Category.BACHE, Category.BASURA, Category.VEREDA):
        for _ in range(5):
            report_on(municipality, TODAY, category=category)
    window = Window("7d", date(2026, 10, 14), TODAY)

    with django_assert_num_queries(3):
        data = distributions(Report.objects.filter(municipality=municipality), window)

    assert data["total"] == 15  # noqa: PLR2004


class TestSeedStatistics:
    """El seed de la demo: sin datos fechados, la sección se ve vacía."""

    def test_it_creates_dated_reports_with_valid_chains(self):
        """CP-023-16 (US-023, nota para la demostración)."""
        from django.core.management import call_command  # noqa: PLC0415
        from django.utils import timezone  # noqa: PLC0415

        from urbancheck.reports.models import ReportStatusHistory  # noqa: PLC0415
        from urbancheck.reports.state_machine import TRANSITIONS  # noqa: PLC0415

        call_command("seed_demo", stdout=None)
        call_command("seed_statistics")
        seeded = Report.objects.filter(description__contains="[stats:")

        assert seeded.count() > 0
        assert seeded.values("category").distinct().count() > 1
        assert seeded.values("status").distinct().count() > 3  # noqa: PLR2004
        allowed = {(t.source, t.target, t.origin) for t in TRANSITIONS}
        now = timezone.now()
        for report in seeded.prefetch_related("status_history"):
            chain = sorted(report.status_history.all(), key=lambda e: e.created_at)
            assert chain[0].status == Status.PENDIENTE_VALIDACION
            assert chain[-1].status == report.status
            for entry in chain[1:]:
                assert (entry.previous_status, entry.status, entry.origin) in allowed
                assert entry.created_at <= now
            assert ReportStatusHistory.objects.filter(report=report).count() == len(
                chain,
            )

    def test_it_is_idempotent(self):
        """CP-023-17."""
        from django.core.management import call_command  # noqa: PLC0415

        call_command("seed_demo")
        call_command("seed_statistics")
        before = Report.objects.count()
        call_command("seed_statistics")

        assert Report.objects.count() == before
