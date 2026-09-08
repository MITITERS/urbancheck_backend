"""Alta de notificaciones desde el resto del dominio.

Se expone como funciones y no como señales de Django para que el disparo quede
explícito y sea fácil de testear desde las vistas que lo provocan.
"""

from .models import Notification
from .push import deliver_push
from .templates_status import message_for

# Fragmento del comentario que se incluye en el aviso, para que el usuario sepa
# de qué se trata sin abrir el reporte.
_PREVIEW_LENGTH = 60


def notify_new_comment(comment) -> Notification | None:
    """Avisa al autor del reporte que alguien comentó (US-009).

    Devuelve ``None`` si el comentario es del propio autor del reporte: nadie
    necesita que le avisen de su propio comentario.
    """
    report = comment.report
    if report.author_id == comment.author_id:
        return None

    preview = comment.text.strip()
    if len(preview) > _PREVIEW_LENGTH:
        preview = preview[:_PREVIEW_LENGTH].rstrip() + "…"

    author_name = comment.author.name or comment.author.email
    notification = Notification.objects.create(
        recipient=report.author,
        actor=comment.author,
        kind=Notification.Kind.NUEVO_COMENTARIO,
        report=report,
        message=f"{author_name} comentó tu reporte: “{preview}”",
    )
    deliver_push(notification)
    return notification


def notify_status_change(
    report,
    *,
    previous_status: str,
    new_status: str,
    changed_by=None,
    reason: str = "",
) -> Notification | None:
    """Avisa al autor del reporte que su reclamo cambió de estado (US-011).

    El destinatario es siempre y únicamente el autor. Si fue él mismo quien
    provocó el cambio, no hay nada que avisarle.

    El push se intenta después de persistir y sin propagar errores: un push
    caído no puede revertir ni bloquear la transición.
    """
    if changed_by is not None and report.author_id == changed_by.id:
        return None

    notification = Notification.objects.create(
        recipient=report.author,
        actor=changed_by,
        kind=Notification.Kind.CAMBIO_ESTADO,
        report=report,
        message=message_for(previous_status, new_status, reason),
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
    )
    deliver_push(notification)
    return notification
