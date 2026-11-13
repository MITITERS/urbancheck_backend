"""US-050 — indicadores de gestión, calculados sobre el historial de transiciones.

Cada test arma el historial a mano, con fechas conocidas, y comprueba el
promedio exacto: un indicador de tiempo mal delimitado le atribuye al municipio
demoras que no le corresponden.
"""

from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.state_machine import Origin
from urbancheck.reports.statistics import Window
from urbancheck.reports.statistics import indicators
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import OperatorFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HOUR = 3600
DAY = 24 * HOUR

URL = "/api/panel/statistics/"
TODAY = date(2026, 10, 20)
ZONE = ZoneInfo(settings.TIME_ZONE)
#: Un momento cómodo dentro de la ventana de 30 días.
T0 = datetime(2026, 10, 1, 10, 0, tzinfo=ZONE)

Status = Report.Status


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr("urbancheck.reports.statistics.today", lambda: TODAY)


@pytest.fixture
def agent():
    return MunicipalAgentFactory.create()


@pytest.fixture
def municipality(agent):
    return agent.municipality


def window() -> Window:
    return Window("30d", date(2026, 9, 21), TODAY)


def with_history(municipality, created_at, steps) -> Report:
    """Un reporte con su historial: ``steps`` es ``[(horas, estado, origen)]``.

    Las horas cuentan desde la creación. El estado final del reporte es el del
    último paso.
    """
    final = steps[-1][1] if steps else Status.PENDIENTE_VALIDACION
    report = ReportFactory.create(
        municipality=municipality,
        status=final,
        with_history=False,
    )
    Report.objects.filter(pk=report.pk).update(created_at=created_at)
    previous = Status.PENDIENTE_VALIDACION
    for hours, status, origin in steps:
        entry = ReportStatusHistory.objects.create(
            report=report,
            previous_status=previous,
            status=status,
            origin=origin,
        )
        ReportStatusHistory.objects.filter(pk=entry.pk).update(
            created_at=created_at + timedelta(hours=hours),
        )
        previous = status
    report.refresh_from_db()
    return report


VALIDATED_FIELD = (Status.REPORTADO, Origin.VALIDACION_TERRENO)
VALIDATED_COLLECTIVE = (Status.REPORTADO, Origin.VALIDACION_COLECTIVA)
PROCESSED = (Status.EN_PROCESO, Origin.MANUAL)
CLOSED = (Status.RESUELTO_PENDIENTE, Origin.CIERRE_OPERARIO)
CONFIRMED = (Status.RESUELTO, Origin.CONFIRMACION_AUTOMATICA)
APPEALED = (Status.EN_PROCESO, Origin.APELACION_CIUDADANO)
CLOSED_FINAL = (Status.RESUELTO, Origin.CIERRE_OPERARIO)


def at(hours, step):
    return (hours, *step)


def compute(municipality) -> dict:
    return indicators(Report.objects.filter(municipality=municipality), window())


class TestValidationTime:
    def test_average_from_creation_to_reported(self, municipality):
        """CP-050-01 (US-050 E1)."""
        with_history(municipality, T0, [at(10, VALIDATED_FIELD)])
        with_history(municipality, T0, [at(30, VALIDATED_FIELD)])

        result = compute(municipality)["validation"]

        assert result["overall"] == {"avg_seconds": 20 * HOUR, "sample_size": 2}

    def test_split_by_origin(self, municipality):
        """CP-050-02 (US-050 E2). Por el origen, no por el rol de quien cambió."""
        with_history(municipality, T0, [at(6, VALIDATED_FIELD)])
        with_history(municipality, T0, [at(48, VALIDATED_COLLECTIVE)])
        with_history(municipality, T0, [at(96, VALIDATED_COLLECTIVE)])

        result = compute(municipality)["validation"]

        assert result["field"] == {"avg_seconds": 6 * HOUR, "sample_size": 1}
        assert result["collective"] == {"avg_seconds": 72 * HOUR, "sample_size": 2}
        assert result["overall"]["avg_seconds"] == pytest.approx(50 * HOUR)
        assert result["overall"]["sample_size"] == 3  # noqa: PLR2004

    def test_only_reports_validated_within_the_period(self, municipality):
        """CP-050-03 (US-050 E1). Creado antes, validado adentro: cuenta."""
        old = datetime(2026, 9, 1, 10, 0, tzinfo=ZONE)
        with_history(municipality, old, [at(30 * 24, VALIDATED_FIELD)])  # 1/10
        with_history(municipality, old, [at(5, VALIDATED_FIELD)])  # 1/9, afuera

        result = compute(municipality)["validation"]

        assert result["overall"]["sample_size"] == 1
        assert result["overall"]["avg_seconds"] == 30 * DAY


class TestAssignmentTime:
    def test_from_reported_to_in_process(self, municipality):
        """CP-050-04 (US-050 E3)."""
        with_history(municipality, T0, [at(10, VALIDATED_FIELD), at(14, PROCESSED)])
        with_history(municipality, T0, [at(10, VALIDATED_FIELD), at(22, PROCESSED)])

        result = compute(municipality)["assignment"]

        assert result == {"avg_seconds": 8 * HOUR, "sample_size": 2}


class TestResolutionTime:
    def test_from_in_process_to_the_operator_close(self, municipality):
        """CP-050-05 (US-050 E4). Termina en el cierre, no en la confirmación."""
        with_history(
            municipality,
            T0,
            [
                at(1, VALIDATED_FIELD),
                at(2, PROCESSED),
                at(26, CLOSED),
                at(26 + 7 * 24, CONFIRMED),
            ],
        )

        result = compute(municipality)["resolution"]

        assert result == {"avg_seconds": 24 * HOUR, "sample_size": 1}

    def test_a_reopened_report_takes_first_start_and_last_close(self, municipality):
        """CP-050-06 (US-050 notas). Lo que el vecino esperó de verdad."""
        with_history(
            municipality,
            T0,
            [
                at(1, VALIDATED_FIELD),
                at(2, PROCESSED),  # primer inicio
                at(12, CLOSED),
                at(20, APPEALED),  # segundo En proceso: no reinicia el reloj
                at(50, CLOSED_FINAL),  # último cierre
            ],
        )

        result = compute(municipality)["resolution"]

        assert result == {"avg_seconds": 48 * HOUR, "sample_size": 1}


class TestOpenReports:
    def test_open_reports_do_not_count_in_averages(self, municipality):
        """CP-050-07 (US-050 E5). Se muestran aparte, con el más viejo."""
        with_history(municipality, T0, [at(10, VALIDATED_FIELD), at(14, PROCESSED)])
        # Lleva mucho En proceso y no tiene cierre: no entra en ningún promedio.
        stale = with_history(
            municipality,
            datetime(2026, 9, 25, 9, 0, tzinfo=ZONE),
            [at(1, VALIDATED_FIELD), at(2, PROCESSED)],
        )
        with_history(municipality, T0, [])

        result = compute(municipality)

        assert result["resolution"]["sample_size"] == 0
        in_process = next(
            row for row in result["open"] if row["status"] == "en_proceso"
        )
        pending = next(
            row for row in result["open"] if row["status"] == "pendiente_validacion"
        )
        assert in_process["count"] == 2  # noqa: PLR2004
        assert in_process["oldest_since"] == stale.created_at + timedelta(hours=2)
        assert in_process["oldest_age_seconds"] > 0
        assert pending["count"] == 1


class TestClosuresAndCancellations:
    def test_appealed_closures_over_all_closures(self, municipality, settings):
        """CP-050-08 (US-050 E6). Y se destaca sobre el umbral configurable."""
        settings.STATS_APPEAL_ALERT_PERCENT = 40
        with_history(
            municipality,
            T0,
            [at(1, VALIDATED_FIELD), at(2, PROCESSED), at(5, CLOSED), at(6, APPEALED)],
        )
        with_history(
            municipality,
            T0,
            [
                at(1, VALIDATED_FIELD),
                at(2, PROCESSED),
                at(5, CLOSED),
                at(200, CONFIRMED),
            ],
        )

        result = compute(municipality)["appealed_closures"]

        assert result["closures"] == 2  # noqa: PLR2004
        assert result["appealed"] == 1
        assert result["percentage"] == 50.0  # noqa: PLR2004
        assert result["alert_threshold"] == 40  # noqa: PLR2004
        assert result["above_threshold"] is True

    def test_cancellations_split_by_origin(self, municipality):
        """CP-050-09 (US-050 E7). Rechazo en terreno ≠ descarte del municipio."""
        with_history(
            municipality,
            T0,
            [at(3, (Status.CANCELADO, Origin.VALIDACION_TERRENO))],
        )
        with_history(
            municipality,
            T0,
            [
                at(3, VALIDATED_FIELD),
                at(5, (Status.CANCELADO, Origin.MODERACION_MUNICIPAL)),
            ],
        )
        with_history(
            municipality,
            T0,
            [
                at(3, VALIDATED_FIELD),
                at(4, PROCESSED),
                at(9, (Status.CANCELADO, Origin.MANUAL)),
            ],
        )

        result = compute(municipality)["cancellations"]

        assert result == {"field_rejection": 1, "moderation": 1, "municipal": 1}

    def test_archived_by_inactivity_is_its_own_indicator(self, municipality):
        """CP-050-10 (US-050 E8). Separado de las cancelaciones."""
        with_history(
            municipality,
            T0,
            [at(3, (Status.ARCHIVADO, Origin.ARCHIVADO_INACTIVIDAD))],
        )

        result = compute(municipality)

        assert result["archived_by_inactivity"] == 1
        assert sum(result["cancellations"].values()) == 0


class TestEmptyAndShared:
    def test_without_closed_cases_the_averages_are_not_available(self, municipality):
        """CP-050-11 (US-050 E10). Nulo, no cero: cero se leería como instantáneo."""
        with_history(municipality, T0, [])

        result = compute(municipality)

        for key in ("assignment", "resolution"):
            assert result[key] == {"avg_seconds": None, "sample_size": 0}
        assert result["validation"]["overall"] == {
            "avg_seconds": None,
            "sample_size": 0,
        }
        assert result["appealed_closures"]["percentage"] is None
        assert result["appealed_closures"]["above_threshold"] is False

    def test_they_travel_with_the_distributions_and_the_same_period(
        self,
        agent,
        municipality,
    ):
        """CP-050-12 (US-050 E9). Un selector, un endpoint."""
        with_history(municipality, T0, [at(10, VALIDATED_FIELD)])
        client = APIClient()
        client.force_authenticate(agent)

        in_30d = client.get(URL).data
        in_7d = client.get(URL, {"period": "7d"}).data

        assert in_30d["indicators"]["validation"]["overall"]["sample_size"] == 1
        assert in_7d["indicators"]["validation"]["overall"]["sample_size"] == 0


class TestJurisdictionAndRoles:
    def test_another_municipality_never_counts(self, agent, municipality):
        """CP-050-13 (US-050 E12)."""
        other = ReportFactory.create().municipality
        with_history(other, T0, [at(10, VALIDATED_FIELD)])
        client = APIClient()
        client.force_authenticate(agent)

        data = client.get(URL).data

        assert data["indicators"]["validation"]["overall"]["sample_size"] == 0

    def test_the_admin_sees_the_municipality_of_its_page(self, municipality):
        """CP-050-14 (US-050 E12)."""
        with_history(municipality, T0, [at(10, VALIDATED_FIELD)])
        with_history(ReportFactory.create().municipality, T0, [at(10, VALIDATED_FIELD)])
        client = APIClient()
        client.force_authenticate(PlatformAdminFactory.create())

        data = client.get(f"/api/municipalities/{municipality.pk}/statistics/").data

        assert data["indicators"]["validation"]["overall"]["sample_size"] == 1

    @pytest.mark.parametrize(
        "factory",
        [UserFactory, ValidatorFactory, OperatorFactory],
        ids=["ciudadano", "validador", "operario"],
    )
    def test_other_roles_get_a_403(self, factory):
        """CP-050-15 (US-050 E12)."""
        client = APIClient()
        client.force_authenticate(factory.create())

        assert client.get(URL).status_code == HTTP_FORBIDDEN


def test_everything_runs_in_the_database(municipality, django_assert_num_queries):
    """CP-050-16 (US-050 DoD). Seis consultas, tenga los reportes que tenga."""
    for hours in (10, 20, 30, 40):
        with_history(
            municipality,
            T0,
            [
                at(hours, VALIDATED_FIELD),
                at(hours + 5, PROCESSED),
                at(hours + 9, CLOSED),
            ],
        )

    with django_assert_num_queries(6):
        result = compute(municipality)

    assert result["resolution"]["sample_size"] == 4  # noqa: PLR2004
