"""Alta de notificaciones desde el resto del dominio.

Se expone como funciones y no como señales de Django para que el disparo quede
explícito y sea fácil de testear desde las vistas que lo provocan.
"""

from .models import Notification

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
    return Notification.objects.create(
        recipient=report.author,
        actor=comment.author,
        kind=Notification.Kind.NUEVO_COMENTARIO,
        report=report,
        message=f"{author_name} comentó tu reporte: “{preview}”",
    )


def notify_status_change(report, changed_by=None) -> Notification | None:
    """Avisa al autor que su reporte cambió de estado."""
    if changed_by is not None and report.author_id == changed_by.id:
        return None
    label = report.get_status_display()
    return Notification.objects.create(
        recipient=report.author,
        actor=changed_by,
        kind=Notification.Kind.CAMBIO_ESTADO,
        report=report,
        message=f"Tu reporte pasó al estado “{label}”.",
    )
