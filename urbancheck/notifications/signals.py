"""Enganche de las notificaciones al evento único de cambio de estado (US-011).

La notificación **no** se dispara desde cada endpoint: escucha el evento que
emite toda transición de la máquina de estados. Si mañana aparece una
transición nueva, el aviso sale solo.
"""

from django.dispatch import receiver

from urbancheck.reports.signals import report_status_changed

from .services import notify_status_change


@receiver(report_status_changed)
def create_status_change_notification(  # noqa: PLR0913 (la firma la fija el Signal)
    sender,
    report,
    previous_status,
    new_status,
    changed_by=None,
    reason="",
    origin="",
    **kwargs,
) -> None:
    notify_status_change(
        report,
        previous_status=previous_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason,
        origin=origin,
    )
