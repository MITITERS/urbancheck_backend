"""Alta de notificaciones desde el resto del dominio.

Se expone como funciones y no como señales de Django para que el disparo quede
explícito y sea fácil de testear desde las vistas que lo provocan.
"""

from django.utils import formats

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


def notify_official_response(response) -> Notification | None:
    """Avisa al autor que el municipio respondió su reporte (US-024).

    El aviso nombra a la **municipalidad** y no al agente: ante el ciudadano
    responde la institución, con el mismo criterio de protección del personal
    que aplica US-038 al validador. La identidad individual solo se ve en el
    panel.
    """
    report = response.report
    if response.author_id is not None and report.author_id == response.author_id:
        return None

    notification = Notification.objects.create(
        recipient=report.author,
        # Sin actor: quien comunica es el municipio, no una persona. Poner al
        # agente acá lo expondría en la bandeja del vecino.
        actor=None,
        kind=Notification.Kind.RESPUESTA_OFICIAL,
        report=report,
        message=(
            f"{response.municipality.city} publicó una respuesta oficial "
            "sobre tu reporte."
        ),
    )
    deliver_push(notification)
    return notification


def notify_upcoming_archival(report, *, archives_on) -> Notification:
    """Avisa al autor que su reporte está por archivarse (US-031).

    Se manda aunque el reporte sea suyo y el disparo sea del sistema: acá no hay
    un tercero que haya hecho algo, y el destinatario es justamente quien puede
    evitarlo.
    """
    notification = Notification.objects.create(
        recipient=report.author,
        # Lo decide la verificación periódica: no hay usuario detrás.
        actor=None,
        kind=Notification.Kind.PROXIMO_ARCHIVADO,
        report=report,
        message=(
            "Tu reporte se archivará el "
            f"{formats.date_format(archives_on, 'd/m/Y')} si no recibe "
            "interacción: todavía no logró validarse."
        ),
    )
    deliver_push(notification)
    return notification


def notify_objection_deadline(report, *, deadline) -> Notification:
    """Avisa al autor que el plazo para objetar el cierre está por vencer (US-047).

    Va al autor y solo al autor: es el único que puede apelar, y el aviso existe
    justamente para que el silencio que confirma el cierre sea un silencio
    informado y no un descuido.
    """
    notification = Notification.objects.create(
        recipient=report.author,
        # Lo decide la verificación periódica: no hay usuario detrás.
        actor=None,
        kind=Notification.Kind.PROXIMA_CONFIRMACION,
        report=report,
        message=(
            "Tu reporte quedará confirmado como resuelto el "
            f"{formats.date_format(deadline, 'd/m/Y')} si no objetás el cierre."
        ),
    )
    deliver_push(notification)
    return notification


def notify_resolution_appealed(appeal) -> list[Notification]:
    """Avisa a los responsables del cierre que el ciudadano lo objetó (US-048).

    Es el único aviso que no va al autor del reporte: acá el autor es quien lo
    dispara. Los destinatarios son quienes tienen que hacer algo con la
    objeción —el operario que cerró y los agentes de la jurisdicción—, y el
    mensaje lleva el motivo para que no tengan que abrir el reporte para saber
    de qué se trata.
    """
    # Import local: ``users`` importa ``reports``, que importa este módulo.
    from urbancheck.users.models import User  # noqa: PLC0415

    report = appeal.report
    recipients = set(
        User.objects.filter(
            role=User.Role.AGENTE_MUNICIPAL,
            municipality_id=report.municipality_id,
            is_work_account_active=True,
        ),
    )
    if appeal.evidence and appeal.evidence.operator:
        recipients.add(appeal.evidence.operator)

    preview = appeal.reason.strip()
    if len(preview) > _PREVIEW_LENGTH:
        preview = preview[:_PREVIEW_LENGTH].rstrip() + "…"

    notifications = []
    for recipient in recipients:
        notification = Notification.objects.create(
            recipient=recipient,
            actor=appeal.author,
            kind=Notification.Kind.APELACION_CIERRE,
            report=report,
            message=f"El vecino objetó el cierre del reporte: “{preview}”",
            reason=appeal.reason,
        )
        deliver_push(notification)
        notifications.append(notification)
    return notifications
