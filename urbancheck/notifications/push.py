"""Envío de push.

**Todavía no hay integración de push en el proyecto.** US-033 implementó la
bandeja in-app, no Firebase, y el modelo de usuario no guarda token de
dispositivo. Este módulo existe para que el punto de envío esté definido y
aislado: cuando se agregue el proveedor, se implementa acá y nada más cambia.

Lo importante hoy es la garantía que ya sostiene: el envío ocurre fuera de la
transacción del cambio de estado y cualquier fallo se traga, de modo que un
push caído no pueda revertir ni bloquear una transición (US-011).
"""

import logging

logger = logging.getLogger(__name__)


def send_push(notification) -> bool:
    """Intenta enviar el aviso como push. Devuelve si se envió.

    Sin integración configurada devuelve ``False``: la notificación igual quedó
    persistida en la bandeja, que es lo que el usuario ve.
    """
    logger.debug(
        "Push no enviado (sin proveedor configurado): notificación %s",
        notification.pk,
    )
    return False


def deliver_push(notification) -> bool:
    """Punto **único** de envío de push.

    Acá y solo acá se consulta la preferencia del usuario (US-025): ninguna
    llamada al servicio de notificaciones puede saltearse el filtro, porque
    ninguna otra ruta llega al envío.

    Un fallo nunca escapa hacia el llamador: el cambio de estado que originó el
    aviso ya está persistido y no puede revertirse por un push caído.
    """
    from .models import NotificationPreference  # noqa: PLC0415

    if not NotificationPreference.is_enabled(notification.recipient, notification.kind):
        logger.debug(
            "Push omitido por preferencia del usuario: notificación %s",
            notification.pk,
        )
        return False

    try:
        return send_push(notification)
    except Exception:
        logger.exception(
            "Falló el envío del push de la notificación %s",
            notification.pk,
        )
        return False
