"""Estadísticas del panel municipal (US-023 y US-050).

Una sola respuesta para toda la sección: el período elegido gobierna las
distribuciones y los indicadores a la vez, y el panel no arma la pantalla con un
pedido por gráfico.

Todo se agrega **en la base**, con ``annotate``/``aggregate``: nunca se traen los
reportes para contarlos en Python. El queryset de partida lo decide quien llama,
y siempre sale de la capa de jurisdicción de US-034 —``for_user`` para el
agente, el municipio de la ficha para el administrador—: acá no hay ningún
filtro por municipalidad que se pueda saltear.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Avg
from django.db.models import Count
from django.db.models import DurationField
from django.db.models import Exists
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Min
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Report
from .models import ReportStatusHistory
from .state_machine import Origin


class Period:
    """Las ventanas que ofrece el selector (US-023, escenario 4)."""

    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_12_MONTHS = "12m"
    CUSTOM = "custom"

    #: Sin elegir nada, la vista arranca con los últimos 30 días (escenario 5).
    DEFAULT = LAST_30_DAYS
    CHOICES = (LAST_7_DAYS, LAST_30_DAYS, LAST_12_MONTHS, CUSTOM)


START_AFTER_END_MESSAGE = "La fecha de inicio no puede ser posterior a la de fin."
FUTURE_DATE_MESSAGE = "El rango no puede incluir fechas futuras."
CUSTOM_NEEDS_DATES_MESSAGE = "Un rango personalizado necesita fecha de inicio y de fin."


class PeriodError(ValueError):
    """Un rango que no se puede aplicar. Lleva el campo y el motivo."""

    def __init__(self, message: str, *, field: str):
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class Window:
    """Un período en días calendario de la zona del municipio, ambos incluidos.

    Se trabaja con fechas y no con instantes porque es lo que elige el agente
    —"del 1 al 15"—, y se traduce a instantes recién al filtrar: ``[start 00:00,
    end + 1 día 00:00)`` en la hora local. Sin eso, un reporte cargado a las 22
    del último día quedaría afuera por la diferencia con UTC.
    """

    key: str
    start: date
    end: date

    def bounds(self) -> tuple[datetime, datetime]:
        zone = ZoneInfo(settings.TIME_ZONE)
        lower = datetime.combine(self.start, time.min, tzinfo=zone)
        upper = datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=zone)
        return lower, upper


def today() -> date:
    return timezone.localdate()


def _a_year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 de febrero
        return day.replace(year=day.year - 1, day=28)


def resolve_window(
    key: str | None,
    start: date | None = None,
    end: date | None = None,
) -> Window:
    """El período pedido, validado (US-023, escenarios 3 a 6).

    La validación vive acá y no solo en el formulario del panel: el rango llega
    del cliente, y un rango invertido o futuro se rechaza con el motivo.
    """
    key = key or Period.DEFAULT
    now = today()
    if key == Period.LAST_7_DAYS:
        return Window(key, now - timedelta(days=6), now)
    if key == Period.LAST_30_DAYS:
        return Window(key, now - timedelta(days=29), now)
    if key == Period.LAST_12_MONTHS:
        return Window(key, _a_year_before(now) + timedelta(days=1), now)
    if key != Period.CUSTOM:
        message = f"Período desconocido: «{key}»."
        raise PeriodError(message, field="period")
    if start is None or end is None:
        raise PeriodError(
            CUSTOM_NEEDS_DATES_MESSAGE,
            field="start" if start is None else "end",
        )
    if start > end:
        raise PeriodError(START_AFTER_END_MESSAGE, field="start")
    if end > now:
        raise PeriodError(FUTURE_DATE_MESSAGE, field="end")
    return Window(key, start, end)


def _with_percentages(counts: dict[str, int], labels, total: int) -> list[dict]:
    """Todas las claves, con cero las que no tienen reportes.

    Así el gráfico no cambia de forma entre períodos. Sin total no hay
    porcentaje: ``None``, no un cero que se leería como un dato (escenario 7).
    """
    return [
        {
            "key": key,
            "label": label,
            "count": counts.get(key, 0),
            "percentage": (
                round(counts.get(key, 0) * 100 / total, 1) if total else None
            ),
        }
        for key, label in labels
    ]


def distributions(reports, window: Window) -> dict:
    """Reportes **creados** en el período, por categoría y por estado (US-023).

    El estado es el actual: la pregunta es "cuánto trabajo tengo abierto de lo
    que entró en este período", y por eso aparecen los siete estados, incluidos
    los que el listado de US-012 no muestra por defecto.

    Tres consultas agregadas en total —el total y dos ``GROUP BY``—, sin traer
    ninguna fila de reporte.
    """
    lower, upper = window.bounds()
    created = reports.filter(created_at__gte=lower, created_at__lt=upper)
    total = created.count()
    by_category = dict(
        created.order_by().values_list("category").annotate(n=Count("pk")),
    )
    by_status = dict(
        created.order_by().values_list("status").annotate(n=Count("pk")),
    )
    return {
        "total": total,
        "by_category": _with_percentages(
            by_category,
            Report.Category.choices,
            total,
        ),
        "by_status": _with_percentages(by_status, Report.Status.choices, total),
    }


# Indicadores de gestión (US-050)
# ------------------------------------------------------------------------------
# Todo sale de ``ReportStatusHistory``, la única fuente de verdad de cuándo
# ocurrió cada transición, y nunca de fechas desnormalizadas en el reporte. Los
# cortes de cada reloj son los de la historia:
#
#   validación   creación del reporte   → primer paso a Reportado
#   asignación   primer paso a Reportado → primer paso a En proceso
#   resolución   primer paso a En proceso → **último** cierre del operario
#
# La resolución termina en el cierre del operario y no en la confirmación: la
# ventana de objeción de US-047 es un control, no tiempo de trabajo municipal.
# Y toma el último cierre porque un reporte reabierto por apelación tiene dos, y
# lo que el vecino esperó es hasta el segundo.
#
# Las restas se hacen en la base con ``ExpressionWrapper(..., DurationField())``
# y se promedian con ``Avg``: no se trae el historial para restar en Python.

Status = Report.Status

#: Los dos caminos a *Reportado*, que se miden por separado (escenario 2).
VALIDATION_ORIGINS = {
    Origin.VALIDACION_TERRENO: "field",
    Origin.VALIDACION_COLECTIVA: "collective",
}

#: Estados abiertos que se muestran aparte de los promedios (escenario 5).
OPEN_STATUSES = (Status.PENDIENTE_VALIDACION, Status.REPORTADO, Status.EN_PROCESO)

#: Las cancelaciones, discriminadas por el origen de la transición (escenario
#: 7). El rechazo del validador lleva ``validacion_terreno``: es una decisión en
#: terreno, como la validación.
CANCELLATION_ORIGINS = {
    Origin.VALIDACION_TERRENO: "field_rejection",
    Origin.MODERACION_MUNICIPAL: "moderation",
    Origin.MANUAL: "municipal",
}


def _history_of(reports):
    return ReportStatusHistory.objects.filter(report__in=reports.values("pk"))


def _first(status: str, **filters) -> Subquery:
    """Cuándo pasó el reporte por primera vez a ``status``."""
    return Subquery(
        ReportStatusHistory.objects.filter(
            report=OuterRef("pk"),
            status=status,
            **filters,
        )
        .order_by("created_at")
        .values("created_at")[:1],
    )


def _last_close() -> Subquery:
    return Subquery(
        ReportStatusHistory.objects.filter(
            report=OuterRef("pk"),
            origin=Origin.CIERRE_OPERARIO,
        )
        .order_by("-created_at")
        .values("created_at")[:1],
    )


def _duration(end: str, start: str) -> ExpressionWrapper:
    return ExpressionWrapper(F(end) - F(start), output_field=DurationField())


def _average(avg, sample_size: int) -> dict:
    """Un promedio con su tamaño de muestra (escenario 11).

    Sin casos es ``None``, no cero: un cero se leería como resolución
    instantánea (escenario 10).
    """
    return {
        "avg_seconds": avg.total_seconds() if avg is not None and sample_size else None,
        "sample_size": sample_size,
    }


def _validation_time(reports, lower, upper) -> dict:
    """Creación → primer paso a Reportado, discriminado por origen (E1, E2).

    Sobre los reportes **validados** dentro del período. Una sola consulta
    agrupada por origen; el promedio total se pondera con los dos grupos.
    """
    first = ReportStatusHistory.objects.filter(
        report=OuterRef("pk"),
        status=Status.REPORTADO,
        origin__in=list(VALIDATION_ORIGINS),
    ).order_by("created_at")
    rows = (
        reports.annotate(
            validated_at=Subquery(first.values("created_at")[:1]),
            validation_origin=Subquery(first.values("origin")[:1]),
        )
        .filter(validated_at__gte=lower, validated_at__lt=upper)
        .annotate(elapsed=_duration("validated_at", "created_at"))
        .order_by()
        .values("validation_origin")
        .annotate(avg=Avg("elapsed"), n=Count("pk"))
    )
    by_origin = {row["validation_origin"]: row for row in rows}
    result = {}
    total_n = 0
    total_seconds = 0.0
    for origin, key in VALIDATION_ORIGINS.items():
        row = by_origin.get(origin)
        n = row["n"] if row else 0
        avg = row["avg"] if row else None
        result[key] = _average(avg, n)
        if n:
            total_n += n
            total_seconds += avg.total_seconds() * n
    result["overall"] = {
        "avg_seconds": total_seconds / total_n if total_n else None,
        "sample_size": total_n,
    }
    return result


def _assignment_time(reports, lower, upper) -> dict:
    """Primer Reportado → primer En proceso (E3), sobre los asignados en el período."""
    stats = (
        reports.annotate(
            reported_at=_first(Status.REPORTADO),
            in_process_at=_first(Status.EN_PROCESO),
        )
        .filter(
            reported_at__isnull=False,
            in_process_at__gte=lower,
            in_process_at__lt=upper,
        )
        .annotate(elapsed=_duration("in_process_at", "reported_at"))
        .aggregate(avg=Avg("elapsed"), n=Count("pk"))
    )
    return _average(stats["avg"], stats["n"])


def _resolution_time(reports, lower, upper) -> dict:
    """Primer En proceso → último cierre del operario (E4), cerrados en el período."""
    stats = (
        reports.annotate(
            in_process_at=_first(Status.EN_PROCESO),
            closed=_last_close(),
        )
        .filter(in_process_at__isnull=False, closed__gte=lower, closed__lt=upper)
        .annotate(elapsed=_duration("closed", "in_process_at"))
        .aggregate(avg=Avg("elapsed"), n=Count("pk"))
    )
    return _average(stats["avg"], stats["n"])


def _open_reports(reports) -> list[dict]:
    """Abiertos ahora, por estado, y desde cuándo espera el más viejo (E5).

    Es una foto del presente y no depende del período: es justamente lo que un
    promedio de casos cerrados esconde. La antigüedad se mide desde que el
    reporte **entró** en ese estado, que es lo que lleva esperando ahí.
    """
    entered = Subquery(
        ReportStatusHistory.objects.filter(
            report=OuterRef("pk"),
            status=OuterRef("status"),
        )
        .order_by("-created_at")
        .values("created_at")[:1],
    )
    rows = (
        reports.filter(status__in=OPEN_STATUSES)
        .annotate(entered_at=Coalesce(entered, F("created_at")))
        .order_by()
        .values("status")
        .annotate(n=Count("pk"), oldest=Min("entered_at"))
    )
    by_status = {row["status"]: row for row in rows}
    now = timezone.now()
    labels = dict(Status.choices)
    result = []
    for status in OPEN_STATUSES:
        row = by_status.get(status)
        oldest = row["oldest"] if row else None
        result.append(
            {
                "status": status,
                "label": labels[status],
                "count": row["n"] if row else 0,
                "oldest_since": oldest,
                "oldest_age_seconds": (now - oldest).total_seconds()
                if oldest
                else None,
            },
        )
    return result


def _appealed_closures(reports, lower, upper) -> dict:
    """Cierres del período y cuántos fueron apelados después (E6).

    Se cuentan **cierres**, no reportes: es la calidad del trabajo ejecutado en
    terreno. Un cierre está apelado si al reporte le sigue una objeción del
    autor.
    """
    appealed_after = ReportStatusHistory.objects.filter(
        report=OuterRef("report"),
        origin=Origin.APELACION_CIUDADANO,
        created_at__gt=OuterRef("created_at"),
    )
    stats = (
        _history_of(reports)
        .filter(
            origin=Origin.CIERRE_OPERARIO,
            created_at__gte=lower,
            created_at__lt=upper,
        )
        .annotate(was_appealed=Exists(appealed_after))
        .aggregate(
            closures=Count("pk"),
            appealed=Count("pk", filter=Q(was_appealed=True)),
        )
    )
    closures = stats["closures"]
    appealed = stats["appealed"]
    percentage = round(appealed * 100 / closures, 1) if closures else None
    threshold = settings.STATS_APPEAL_ALERT_PERCENT
    return {
        "closures": closures,
        "appealed": appealed,
        "percentage": percentage,
        "alert_threshold": threshold,
        "above_threshold": percentage is not None and percentage > threshold,
    }


def _cancellations(reports, lower, upper) -> dict:
    """Cancelaciones del período por origen (E7), y archivados por inactividad (E8).

    Una sola consulta agrupada por (estado, origen) sobre el historial.
    """
    rows = (
        _history_of(reports)
        .filter(
            created_at__gte=lower,
            created_at__lt=upper,
            status__in=[Status.CANCELADO, Status.ARCHIVADO],
        )
        .order_by()
        .values_list("status", "origin")
        .annotate(n=Count("pk"))
    )
    cancellations = dict.fromkeys(CANCELLATION_ORIGINS.values(), 0)
    archived = 0
    for status, origin, n in rows:
        if status == Status.CANCELADO and origin in CANCELLATION_ORIGINS:
            cancellations[CANCELLATION_ORIGINS[origin]] += n
        elif status == Status.ARCHIVADO and origin == Origin.ARCHIVADO_INACTIVIDAD:
            archived += n
    return {"cancellations": cancellations, "archived_by_inactivity": archived}


def indicators(reports, window: Window) -> dict:
    """Los indicadores de gestión de US-050, sobre el mismo período."""
    lower, upper = window.bounds()
    return {
        "validation": _validation_time(reports, lower, upper),
        "assignment": _assignment_time(reports, lower, upper),
        "resolution": _resolution_time(reports, lower, upper),
        "open": _open_reports(reports),
        "appealed_closures": _appealed_closures(reports, lower, upper),
        **_cancellations(reports, lower, upper),
    }


def build_statistics(reports, window: Window) -> dict:
    """La respuesta entera de la sección de estadísticas (US-023 y US-050).

    Un solo endpoint para toda la sección: los indicadores viajan en la misma
    respuesta que las distribuciones, sobre el mismo período.
    """
    return {
        "period": {"key": window.key, "start": window.start, "end": window.end},
        **distributions(reports, window),
        "indicators": indicators(reports, window),
    }
