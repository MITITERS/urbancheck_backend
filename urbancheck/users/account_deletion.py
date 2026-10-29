"""Baja de cuenta por el propio vecino (N-09 y N-17, art. 16 de la Ley 25.326).

Decisión del equipo sobre qué se borra y qué se conserva:

- **Se borran** los reportes que el municipio nunca gestionó: los que nunca
  salieron de *Pendiente de validación* (siguen ahí, o el vecino los canceló, o
  se archivaron por inactividad) y no recibieron ninguna acción de un tercero.
- **Se conservan sin autor** los que tuvieron gestión municipal: llegaron a
  *Reportado* o más allá, o los rechazó un validador, los descartó el
  municipio o tienen una respuesta oficial. Sus apelaciones, también sin autor.
- **Se borran** sus comentarios, sus me gusta, sus avisos y sus sesiones.

Los archivos (fotos y avatar) los borra ``media_cleanup`` al confirmarse la
transacción (N-08). Las cuentas de trabajo no pasan por acá: siguen con la baja
lógica, porque su nombre es parte del historial de gestión.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Q

from urbancheck.common.security import log_event
from urbancheck.reports.models import ModerationDecision
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory

from .signals import close_sessions

#: Los estados en los que puede quedar un reporte que el municipio no tocó.
UNHANDLED_STATUSES = frozenset(
    {
        Report.Status.PENDIENTE_VALIDACION,
        Report.Status.CANCELADO,
        Report.Status.ARCHIVADO,
    },
)


def unhandled_reports(user):
    """Los reportes de ``user`` que el municipio nunca gestionó."""
    report = OuterRef("pk")
    handled_history = ReportStatusHistory.objects.filter(report=report).filter(
        ~Q(status__in=UNHANDLED_STATUSES)
        | (Q(changed_by__isnull=False) & ~Q(changed_by=user)),
    )
    return (
        Report.objects.filter(author=user, status__in=UNHANDLED_STATUSES)
        .exclude(Exists(handled_history))
        .exclude(Exists(OfficialResponse.objects.filter(report=report)))
        .exclude(Exists(ModerationDecision.objects.filter(report=report)))
    )


@transaction.atomic
def delete_citizen_account(user, *, request=None) -> dict[str, int]:
    """Borra la cuenta de un vecino según la decisión del equipo."""
    unhandled = unhandled_reports(user)
    deleted = unhandled.count()
    unhandled.delete()
    kept = Report.objects.filter(author=user).count()
    close_sessions(user)
    log_event(
        "account_deleted",
        request=request,
        user_id=user.pk,
        reports_deleted=deleted,
        reports_kept=kept,
    )
    # Comentarios, me gusta y avisos propios caen en cascada; los reportes que
    # quedan y sus apelaciones pasan a autor nulo (``SET_NULL``).
    user.delete()
    return {"reports_deleted": deleted, "reports_kept": kept}
