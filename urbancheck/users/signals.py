"""Efectos de dominio sobre el usuario disparados por allauth."""

from allauth.account.signals import password_changed
from allauth.account.signals import password_reset
from django.dispatch import receiver


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
