"""Efectos de dominio sobre el usuario disparados por allauth."""

from allauth.account.signals import password_changed
from allauth.account.signals import password_reset
from allauth.account.signals import password_set
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from django.utils import timezone


@receiver([password_changed, password_reset])
def clear_temporary_password_flag(sender, request, user, **kwargs) -> None:
    """El primer cambio de contraseña levanta el bloqueo del alta (US-017).

    Se engancha al evento de allauth y no al endpoint, para que valga tanto para
    el cambio desde el panel como para el que llega por recuperación: en los dos
    casos el usuario ya eligió una contraseña propia.
    """
    if not user.must_change_password:
        return
    user.must_change_password = False
    user.save(update_fields=["must_change_password"])


def close_sessions(user, *, keep: str | None = None) -> int:
    """Borra las sesiones abiertas de ``user``, salvo la de clave ``keep``.

    Alcanza también a las de la app y el panel: el ``X-Session-Token`` de
    allauth headless es la clave de una sesión de Django. Las sesiones no se
    indexan por usuario, así que se decodifican las vigentes.
    """
    closed = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.session_key == keep:
            continue
        if session.get_decoded().get(SESSION_KEY) == str(user.pk):
            closed.append(session.session_key)
    Session.objects.filter(session_key__in=closed).delete()
    return len(closed)


@receiver([password_changed, password_set])
def close_other_sessions(sender, request, user, **kwargs) -> None:
    """Con la contraseña nueva, las demás sesiones se cierran (N-04).

    La sesión desde la que se cambió sigue abierta: quien la cambió está ahí.
    Sin esto, un token robado sobrevivía al cambio hasta vencer.
    """
    session = getattr(request, "session", None)
    close_sessions(user, keep=session.session_key if session is not None else None)


@receiver(password_reset)
def close_every_session(sender, request, user, **kwargs) -> None:
    """La recuperación se hace sin sesión, así que se cierran todas (N-04)."""
    close_sessions(user)
