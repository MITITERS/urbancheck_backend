"""Eventos de seguridad que se enganchan a señales y no a una vista.

El login, los cambios de contraseña y las altas de cuentas de trabajo llegan
por más de un camino —la API headless, las páginas de allauth, el admin de
Django—. Engancharse a la señal los cubre a todos sin repetir el registro en
cada vista. Lo importa ``UsersConfig.ready``.
"""

from __future__ import annotations

import hashlib

from allauth.account.signals import password_changed
from allauth.account.signals import password_reset
from allauth.account.signals import password_set
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.signals import user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from urbancheck.municipalities.models import Municipality
from urbancheck.users.models import User

from .security import log_event


def account_fingerprint(login: str) -> str:
    """Huella de la cuenta que se intentó usar, sin guardar lo que se escribió.

    Alcanza para ver que alguien prueba contraseñas contra la misma cuenta. El
    texto tal cual no se registra: si el usuario escribió la contraseña en el
    campo del correo, quedaría en el archivo.
    """
    digest = hashlib.sha256(login.strip().lower().encode()).hexdigest()
    return digest[:16]


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs) -> None:
    log_event("login_succeeded", request=request, user_id=user.pk)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs) -> None:
    # Django ya enmascara la contraseña en ``credentials``; igual se toma solo
    # el identificador.
    login = credentials.get("email") or credentials.get("username") or ""
    log_event(
        "login_failed",
        request=request,
        user_id=None,
        account=account_fingerprint(login) if login else None,
    )


@receiver(password_changed)
def log_password_changed(sender, request, user, **kwargs) -> None:
    log_event("password_changed", request=request, user_id=user.pk)


@receiver(password_set)
def log_password_set(sender, request, user, **kwargs) -> None:
    log_event("password_set", request=request, user_id=user.pk)


@receiver(password_reset)
def log_password_reset(sender, request, user, **kwargs) -> None:
    log_event("password_reset", request=request, user_id=user.pk)


@receiver(post_save, sender=User)
def log_work_account_created(sender, instance, created, **kwargs) -> None:
    """Alta de agente, validador u operario, la haga el panel o el admin.

    ``user_id`` es quien da el alta, que sale del request en curso; la cuenta
    creada va en ``account``.
    """
    if not created or instance.role not in User.WORK_ROLES:
        return
    log_event(
        "work_account_created",
        account=instance.pk,
        role=instance.role,
        municipality=instance.municipality_id,
    )


@receiver(post_save, sender=Municipality)
def log_municipality_created(sender, instance, created, **kwargs) -> None:
    if created:
        log_event("municipality_created", municipality=instance.pk)
