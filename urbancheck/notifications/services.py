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


def notify_status_change(  # noqa: PLR0913 (cada uno es un dato del aviso)
    report,
    *,
    previous_status: str,
    new_status: str,
    changed_by=None,
    reason: str = "",
    origin: str = "",
) -> Notification | None:
    """Avisa al autor del reporte que su reclamo cambió de estado (US-011).

    El destinatario es siempre y únicamente el autor. Si fue él mismo quien
    provocó el cambio, no hay nada que avisarle.

    El ``origin`` desempata los pares de estados que significan más de una cosa:
    sin él, una validación colectiva se le anunciaba al vecino como si un
    validador hubiera ido al lugar.

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
        message=message_for(previous_status, new_status, reason, origin),
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


def notify_image_removed(
    report,
    *,
    from_resolution_evidence: bool,
    still_hidden: bool = False,
) -> Notification:
    """Avisa al autor qué se retiró por protección de datos (US-043).

    Son dos consecuencias distintas y el mensaje dice cuál:

    - **La foto del reporte**: se retira el reporte entero, para siempre. Un
      reporte sin foto no se vuelve a publicar. Se le dice que puede volver a
      reportar el problema con otra foto, para que no se quede sin reclamo.
    - **La foto de un cierre del operario**: el reporte conserva la suya y
      sigue como estaba, salvo que otra imagen lo mantenga en revisión.

    No lleva ``actor``, aunque lo decidió un administrador: ante el vecino
    responde la plataforma, con el mismo criterio de protección del personal
    de US-038. Quién resolvió queda en el registro de la solicitud.
    """
    if not from_resolution_evidence:
        message = (
            "Retiramos tu reporte porque su foto mostraba un rostro o una patente "
            "sin difuminar. Ya no está publicado; si el problema sigue, podés "
            "reportarlo de nuevo con otra foto."
        )
    elif still_hidden:
        message = (
            "Retiramos la foto del trabajo realizado en tu reporte porque mostraba "
            "un dato personal. El reporte sigue oculto mientras revisamos otra de "
            "sus imágenes."
        )
    else:
        message = (
            "Retiramos la foto del trabajo realizado en tu reporte porque mostraba "
            "un dato personal. El reporte sigue publicado como estaba."
        )
    notification = Notification.objects.create(
        recipient=report.author,
        actor=None,
        kind=Notification.Kind.IMAGEN_RETIRADA,
        report=report,
        message=message,
    )
    deliver_push(notification)
    return notification


def notify_report_under_review(report) -> Notification:
    """Avisa al autor que su reporte se ocultó por una denuncia (US-043).

    Sin este aviso el vecino descubría que su reclamo desapareció del feed sin
    saber por qué. **No dice quién denunció**: la denuncia es de cualquier
    vecino y exponerlo invitaría a la represalia. Quien decide si corresponde
    mandarlo —no, si el que denunció es el propio autor— es el servicio.
    """
    notification = Notification.objects.create(
        recipient=report.author,
        actor=None,
        kind=Notification.Kind.REPORTE_EN_REVISION,
        report=report,
        message=(
            "Ocultamos tu reporte mientras revisamos una denuncia sobre su "
            "imagen: puede mostrar un rostro o una patente sin difuminar."
        ),
    )
    deliver_push(notification)
    return notification


def notify_complaint_received(complaint, *, message: str) -> Notification:
    """Le deja a quien denunció el acuse de su denuncia (US-021).

    Es el mismo texto que ve al confirmar, que distingue quién la revisa: queda
    en sus avisos para cuando cierre la pantalla.
    """
    notification = Notification.objects.create(
        recipient=complaint.reporter,
        actor=None,
        kind=Notification.Kind.DENUNCIA_RECIBIDA,
        report=complaint.report,
        message=message,
    )
    deliver_push(notification)
    return notification


def notify_report_reported(report) -> Notification:
    """Avisa al autor que su reporte recibió una denuncia de contenido (US-021).

    **No dice quién denunció ni por qué motivo**, y va sin ``actor``: el
    escenario 9 reserva la identidad del denunciante para quien resuelve. Que
    tampoco delate cuántas denuncias hay lo cuida el servicio, que lo manda una
    sola vez mientras haya alguna pendiente.
    """
    notification = Notification.objects.create(
        recipient=report.author,
        actor=None,
        kind=Notification.Kind.REPORTE_DENUNCIADO,
        report=report,
        message=(
            "Otro vecino denunció tu reporte. Lo va a revisar el municipio; "
            "mientras tanto sigue publicado."
        ),
    )
    deliver_push(notification)
    return notification


def notify_report_restored(report) -> Notification:
    """Avisa al autor que la denuncia se desestimó (US-043, escenario 6)."""
    notification = Notification.objects.create(
        recipient=report.author,
        actor=None,
        kind=Notification.Kind.REPORTE_RESTITUIDO,
        report=report,
        message=(
            "Revisamos la imagen de tu reporte y no muestra datos personales: "
            "volvió a publicarse tal como estaba."
        ),
    )
    deliver_push(notification)
    return notification


def notify_photo_processing_failed(instance, *, report=None) -> Notification | None:
    """Avisa que una imagen no se pudo difuminar y por eso no se publicó (US-042).

    Un solo tipo de aviso para los tres orígenes, con el destinatario y el texto
    que corresponden a cada uno: quien tiene que enterarse es siempre quien
    subió la foto, y lo que necesita saber es lo mismo —no se publicó, y puede
    volver a cargarla—.

    El aviso puede no tener destinatario: la cuenta del operario que cerró pudo
    borrarse desde entonces. En ese caso no se manda nada y el caso queda en el
    log y en el panel, que es donde se diagnostica.
    """
    recipient = getattr(instance, "author", None) or getattr(instance, "operator", None)
    if recipient is None:
        return None

    kind = type(instance).__name__
    if kind == "ResolutionEvidence":
        message = (
            "No pudimos procesar la foto de tu cierre y no se publicó. El parte "
            "de trabajo quedó registrado: volvé a cargar la foto."
        )
    elif kind == "ResolutionAppeal":
        message = (
            "No pudimos procesar la foto de tu objeción y no se publicó. "
            "Volvé a cargarla para que el municipio pueda verla."
        )
    else:
        message = (
            "No pudimos procesar la imagen de tu reporte, así que no llegó a "
            "publicarse. Volvé a cargarlo con otra foto."
        )

    notification = Notification.objects.create(
        recipient=recipient,
        actor=None,
        kind=Notification.Kind.IMAGEN_NO_PROCESADA,
        report=report if report is not None else getattr(instance, "report", instance),
        message=message,
    )
    deliver_push(notification)
    return notification


def notify_complaint_resolved(
    report,
    *,
    recipients,
    image_removed: bool,
    report_withdrawn: bool = False,
) -> list:
    """Le cuenta a quien denunció qué se decidió (US-043).

    Cierra el circuito de quien avisó: sin esto, denunciaba y nunca sabía si
    sirvió. Recibe los destinatarios ya filtrados —el autor del reporte no, que
    tiene su propio aviso—.
    """
    if report_withdrawn:
        message = (
            "Retiramos el reporte que denunciaste: su foto mostraba un dato "
            "personal. Gracias por avisar."
        )
    elif image_removed:
        message = (
            "Retiramos la imagen que denunciaste: mostraba un dato personal. "
            "Gracias por avisar."
        )
    else:
        message = (
            "Revisamos la imagen que denunciaste y no muestra datos personales, "
            "así que el reporte volvió a publicarse."
        )
    notifications = []
    for recipient in recipients:
        notification = Notification.objects.create(
            recipient=recipient,
            actor=None,
            kind=Notification.Kind.DENUNCIA_RESUELTA,
            report=report,
            message=message,
        )
        deliver_push(notification)
        notifications.append(notification)
    return notifications
