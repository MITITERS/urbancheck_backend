"""Moderación municipal de denuncias por contenido (US-049).

El agente municipal resuelve las denuncias por contenido inapropiado o reporte
falso de su jurisdicción. No existe un rol moderador: el agente ya conoce el
territorio y ya opera la máquina de estados.

Darle al municipio la facultad de sacar reclamos de la vista pública es un
riesgo asumido, y por eso tiene cuatro contrapesos que no son opcionales:

1. El motivo de la decisión es **público** en el detalle del reporte.
2. El autor puede **apelar**. La apelación la resuelven el administrador de la
   plataforma —todas— y el agente de la jurisdicción —las de su municipio—.
   La historia la dejaba solo en manos de la plataforma; que el agente también
   la resuelva es una decisión del usuario del 20/10.
3. El administrador puede **revertir** cualquier descarte, también de oficio.
4. US-050 cuenta los descartes por moderación como indicador propio.

Las denuncias se resuelven **por reporte, no una por una** (escenario 2): una
sola decisión cierra todas las pendientes de contenido. Las de dato personal
quedan fuera —las resuelve el administrador según US-043— porque la consulta
parte de ``for_municipal_review()``.
"""

from __future__ import annotations

from django.db import IntegrityError
from django.db import transaction
from django.db.models import Count
from django.db.models import IntegerField
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.common.security import log_event
from urbancheck.notifications.services import notify_content_complaints_resolved
from urbancheck.notifications.services import notify_moderation_appeal_rejected

from .models import ModerationDecision
from .models import Report
from .models import ReportComplaint
from .models import ResolutionAppeal
from .services import apply_transition
from .state_machine import Actor
from .state_machine import restore_operation

REASON_REQUIRED_MESSAGE = "Indicá el motivo de tu decisión."
NOTHING_TO_RESOLVE_MESSAGE = (
    "Este reporte ya no tiene denuncias por contenido pendientes: otra decisión "
    "llegó antes."
)
NOT_APPEALABLE_MESSAGE = "Este reporte no tiene un descarte por moderación vigente."
ALREADY_APPEALED_MESSAGE = (
    "Ya apelaste este descarte. La decisión sobre la apelación es definitiva."
)
APPEAL_ALREADY_RESOLVED_MESSAGE = "Esta apelación ya fue resuelta."
NOT_AUTHOR_MESSAGE = "Solo el autor del reporte puede apelar el descarte."


def pending_content_complaints():
    """Cuántas denuncias por contenido esperan decisión, por reporte (US-049).

    Una subconsulta y no un ``Count`` sobre la relación: el queryset del panel
    ya cuenta likes y respuestas con joins, y un join más multiplicaría filas.
    """
    counts = (
        ReportComplaint.objects.for_municipal_review()
        .filter(report=OuterRef("pk"), status=ReportComplaint.Status.PENDIENTE)
        .order_by()
        .values("report")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)


class ModerationError(Exception):
    """Una decisión de moderación que no se puede ejecutar."""


class ReasonRequiredError(ModerationError):
    """Toda decisión lleva motivo (escenario 5)."""


class NothingToResolveError(ModerationError):
    """No quedan denuncias pendientes: otra pestaña ya resolvió."""


class NotAppealableError(ModerationError):
    """El reporte no tiene un descarte vigente que apelar o revertir."""


class AlreadyAppealedError(ModerationError):
    """El descarte ya tuvo su única apelación."""


class AppealAlreadyResolvedError(ModerationError):
    """La apelación ya no está pendiente."""


class NotAuthorError(ModerationError):
    """Solo el autor apela."""


def _clean(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise ReasonRequiredError(REASON_REQUIRED_MESSAGE)
    return reason


def _lock_pending_complaints(report: Report) -> list[ReportComplaint]:
    pending = list(
        ReportComplaint.objects.for_municipal_review()
        .select_for_update(of=("self",))
        .filter(report=report, status=ReportComplaint.Status.PENDIENTE)
        .select_related("reporter"),
    )
    if not pending:
        raise NothingToResolveError(NOTHING_TO_RESOLVE_MESSAGE)
    return pending


def _close(complaints, *, decision: ModerationDecision, status: str, agent) -> None:
    ReportComplaint.objects.filter(pk__in=[c.pk for c in complaints]).update(
        status=status,
        resolved_at=decision.created_at,
        resolved_by=agent,
        moderation_decision=decision,
    )


def _reporters(complaints) -> list:
    """Quiénes denunciaron, una vez cada uno."""
    seen = {}
    for complaint in complaints:
        if complaint.reporter_id and complaint.reporter_id not in seen:
            seen[complaint.reporter_id] = complaint.reporter
    return list(seen.values())


def discard_report(report: Report, *, agent, reason: str) -> ModerationDecision:
    """El reporte es falso, inexistente u ofensivo (escenario 3).

    Una sola transacción: la decisión, la transición a Cancelado —por la
    máquina de estados única, con origen ``moderacion_municipal`` y el agente
    en el historial— y el cierre de todas las denuncias. Si cualquiera falla,
    no queda ninguna de las tres.

    El estado previo se guarda en la decisión para que el administrador pueda
    restituirlo tal cual (escenarios 7 y 8). El aviso al autor, con el motivo,
    sale del evento de cambio de estado como cualquier otra transición.
    """
    reason = _clean(reason)
    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        complaints = _lock_pending_complaints(locked)
        decision = ModerationDecision.objects.create(
            report=locked,
            outcome=ModerationDecision.Outcome.DESCARTADO,
            reason=reason,
            previous_status=locked.status,
            decided_by=agent,
        )
        apply_transition(
            locked,
            "descartar_por_moderacion",
            actor=Actor.MUNICIPAL_AGENT,
            changed_by=agent,
            reason=reason,
        )
        _close(
            complaints,
            decision=decision,
            status=ReportComplaint.Status.REPORTE_DESCARTADO,
            agent=agent,
        )
        notify_content_complaints_resolved(
            locked,
            recipients=_reporters(complaints),
            discarded=True,
        )
    log_event(
        "moderation_discard",
        report_id=report.pk,
        decision_id=decision.pk,
        complaints=len(complaints),
    )
    report.refresh_from_db()
    return decision


def dismiss_complaints(report: Report, *, agent, reason: str) -> ModerationDecision:
    """El reporte es legítimo: las denuncias se desestiman (escenario 4).

    El reporte conserva estado y visibilidad: no hay transición. Que los mismos
    vecinos no puedan volver a denunciarlo por el mismo motivo ya lo garantiza
    ``unique_content_complaint_per_reason``, que es permanente.
    """
    reason = _clean(reason)
    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        complaints = _lock_pending_complaints(locked)
        decision = ModerationDecision.objects.create(
            report=locked,
            outcome=ModerationDecision.Outcome.DESESTIMADO,
            reason=reason,
            decided_by=agent,
        )
        _close(
            complaints,
            decision=decision,
            status=ReportComplaint.Status.DESESTIMADA,
            agent=agent,
        )
        notify_content_complaints_resolved(
            locked,
            recipients=_reporters(complaints),
            discarded=False,
        )
    log_event(
        "moderation_dismiss",
        report_id=report.pk,
        decision_id=decision.pk,
        complaints=len(complaints),
    )
    return decision


def appeal_moderation(report: Report, *, author, reason: str) -> ResolutionAppeal:
    """El autor apela el descarte (escenario 6).

    Reutiliza el modelo de apelaciones de US-048 con el tipo ``moderacion``.
    No mueve el estado: el reporte sigue Cancelado mientras se revisa. La
    restricción única por decisión es la que tiene la última palabra ante dos
    pedidos simultáneos.
    """
    if report.author_id != author.pk:
        raise NotAuthorError(NOT_AUTHOR_MESSAGE)
    reason = _clean(reason)
    decision = report.active_discard()
    if decision is None:
        raise NotAppealableError(NOT_APPEALABLE_MESSAGE)
    if decision.appeals.exists():
        raise AlreadyAppealedError(ALREADY_APPEALED_MESSAGE)
    try:
        with transaction.atomic():
            appeal = ResolutionAppeal.objects.create(
                report=report,
                kind=ResolutionAppeal.Kind.MODERACION,
                moderation_decision=decision,
                author=author,
                reason=reason,
                status=ResolutionAppeal.Status.PENDIENTE,
                # No lleva foto: no hay nada que difuminar ni que esperar.
                photo_status=PhotoStatus.PROCESADA,
            )
    except IntegrityError as error:
        raise AlreadyAppealedError(ALREADY_APPEALED_MESSAGE) from error
    log_event("moderation_appeal", report_id=report.pk, appeal_id=appeal.pk)
    return appeal


def _actor_for(reviewer) -> Actor:
    return Actor.PLATFORM_ADMIN if reviewer.is_platform_admin else Actor.MUNICIPAL_AGENT


def revert_moderation(
    report: Report,
    *,
    reviewer,
    reason: str,
) -> ModerationDecision:
    """Restituye un reporte descartado (escenarios 7 y 8).

    De oficio solo lo hace el administrador (lo controla la vista); al hacer
    lugar a una apelación, también el agente de la jurisdicción.

    Lo devuelve al estado que tenía antes del descarte por la operación
    ``restituir_a_<estado>``, cuya guarda verifica que el destino sea ese y no
    otro. La transición queda en el historial con quien revisó y origen
    ``reversion_moderacion``, y recupera la visibilidad sola: la visibilidad se
    deduce del estado, no de una marca paralela.
    """
    reason = _clean(reason)
    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        decision = locked.active_discard()
        if decision is None:
            raise NotAppealableError(NOT_APPEALABLE_MESSAGE)
        apply_transition(
            locked,
            restore_operation(decision.previous_status),
            actor=_actor_for(reviewer),
            changed_by=reviewer,
            reason=reason,
        )
        decision.reverted_at = timezone.now()
        decision.reverted_by = reviewer
        decision.revert_reason = reason
        decision.save(update_fields=["reverted_at", "reverted_by", "revert_reason"])
    log_event("moderation_revert", report_id=report.pk, decision_id=decision.pk)
    report.refresh_from_db()
    return decision


def resolve_moderation_appeal(
    appeal: ResolutionAppeal,
    *,
    reviewer,
    accept: bool,
    reason: str,
) -> ResolutionAppeal:
    """Hacer lugar o no a la apelación (escenario 7).

    ``reviewer`` es el administrador o el agente de la jurisdicción del
    reporte: que pertenezca a ella lo garantiza la vista, que solo le muestra
    las apelaciones de su municipio.

    Si hace lugar, es la misma reversión que la de oficio. Si no, el reporte
    queda Cancelado y no admite una segunda apelación: la restricción única por
    decisión lo impide aunque el autor lo intente.
    """
    reason = _clean(reason)
    with transaction.atomic():
        locked = ResolutionAppeal.objects.select_for_update(of=("self",)).get(
            pk=appeal.pk,
        )
        if (
            locked.kind != ResolutionAppeal.Kind.MODERACION
            or locked.status != ResolutionAppeal.Status.PENDIENTE
        ):
            raise AppealAlreadyResolvedError(APPEAL_ALREADY_RESOLVED_MESSAGE)
        if accept:
            revert_moderation(locked.report, reviewer=reviewer, reason=reason)
        locked.status = (
            ResolutionAppeal.Status.ACEPTADA
            if accept
            else ResolutionAppeal.Status.RECHAZADA
        )
        locked.resolved_at = timezone.now()
        locked.resolved_by = reviewer
        locked.resolution_reason = reason
        locked.save(
            update_fields=["status", "resolved_at", "resolved_by", "resolution_reason"],
        )
        if not accept:
            notify_moderation_appeal_rejected(locked)
    log_event(
        "moderation_appeal_resolved",
        appeal_id=appeal.pk,
        accepted=accept,
    )
    return locked
