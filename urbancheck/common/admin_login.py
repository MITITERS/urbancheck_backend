"""Límite de intentos del login del admin de Django (N-02).

La API ya limita los logins con allauth (``ACCOUNT_RATE_LIMITS["login_failed"]``),
pero el admin tiene su propio formulario. Antes podía mandarse por allauth con
``DJANGO_ADMIN_FORCE_ALLAUTH``; con ``HEADLESS_ONLY`` (N-16) esas vistas no
existen, así que el admin lleva acá la misma política, leída del mismo valor:
5 intentos fallidos por cuenta en 15 minutos y 10 por minuto por IP.

Como en allauth, la ventana es deslizante (se guarda la marca de cada intento
fallido y se cuentan los del período), los contadores viven en el cache
compartido (Redis) y, una vez alcanzado el tope, se rechaza también la
contraseña correcta: si no, el bloqueo le avisaría a quien prueba que acertó.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from .security import client_ip
from .security import log_event
from .security_receivers import account_fingerprint

if TYPE_CHECKING:
    from django.http import HttpRequest

LOCKED_MESSAGE = (
    "Hiciste demasiados intentos seguidos. Esperá unos minutos y probá de nuevo."
)

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_rates(value: str) -> list[tuple[int, int, str]]:
    """``"10/m/ip,5/15m/key"`` → ``[(10, 60, "ip"), (5, 900, "key")]``."""
    rates = []
    for rate in filter(None, (part.strip() for part in value.split(","))):
        amount, period, kind = rate.split("/")
        multiplier = int(period[:-1]) if len(period) > 1 else 1
        rates.append((int(amount), multiplier * _UNITS[period[-1]], kind))
    return rates


def _keys(request: HttpRequest, login: str) -> list[tuple[str, int, int]]:
    """Las claves del cache que cuentan este intento, con su tope y su ventana."""
    keys = []
    for amount, window, kind in _parse_rates(
        settings.ACCOUNT_RATE_LIMITS["login_failed"],
    ):
        subject = account_fingerprint(login) if kind == "key" else client_ip(request)
        keys.append((f"admin-login:{kind}:{window}:{subject}", amount, window))
    return keys


def _recent(key: str, window: int, now: float) -> list[float]:
    return [stamp for stamp in cache.get(key, []) if stamp > now - window]


def is_locked(request: HttpRequest, login: str) -> bool:
    now = time.time()
    return any(
        len(_recent(key, window, now)) >= amount
        for key, amount, window in _keys(request, login)
    )


def record_failure(request: HttpRequest, login: str) -> None:
    now = time.time()
    for key, _amount, window in _keys(request, login):
        cache.set(key, [*_recent(key, window, now), now], timeout=window)


def limit_admin_login(login_view):
    """Envuelve ``admin.site.login`` con el límite de intentos."""

    @wraps(login_view)
    def wrapper(request: HttpRequest, extra_context=None):
        if request.method != "POST":
            return login_view(request, extra_context)
        login = request.POST.get("username", "")
        if is_locked(request, login):
            log_event(
                "login_locked",
                request=request,
                account=account_fingerprint(login) if login else None,
            )
            return HttpResponse(
                LOCKED_MESSAGE,
                status=429,
                content_type="text/plain; charset=utf-8",
            )
        response = login_view(request, extra_context)
        # El admin vuelve a dibujar el formulario (200) cuando el ingreso
        # falla, también si la cuenta existe pero no es de staff; si entra,
        # redirige.
        if response.status_code == 200 and not request.user.is_authenticated:  # noqa: PLR2004
            record_failure(request, login)
        return response

    return wrapper
