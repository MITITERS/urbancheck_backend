"""Registro de eventos de seguridad y resolución de la IP del cliente.

Todo lo que el documento de Seguridad pide auditar pasa por ``log_event``, que
escribe en el logger ``security`` (archivo rotado, ver ``LOGGING`` en
``config/settings/base.py``). Cada registro lleva la marca temporal del
formatter más el usuario, la IP y la ruta del pedido en curso.

**Lo que nunca se registra:** contraseñas, tokens, cookies ni cuerpos de
solicitud. ``log_event`` no recibe el request entero a propósito: solo los
campos que se le pasan por nombre, más los tres que toma del contexto.

El contexto lo pone ``SecurityContextMiddleware``. Así un receiver de
``post_save`` —el alta de un agente desde el admin, por ejemplo— sabe quién y
desde dónde la hizo sin que cada vista tenga que pasárselo.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING

from django.conf import settings
from django.middleware.csp import ContentSecurityPolicyMiddleware

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http import HttpResponse

logger = logging.getLogger("security")

#: Las respuestas que se registran siempre, venga de donde venga el rechazo.
LOGGED_STATUSES = frozenset({401, 403, 429})

_current_request: ContextVar[HttpRequest | None] = ContextVar(
    "security_request",
    default=None,
)


def client_ip(request: HttpRequest | None) -> str | None:
    """La IP real del cliente, contando los proxies de confianza.

    Es el mismo criterio que ``NUM_PROXIES`` de DRF y
    ``ALLAUTH_TRUSTED_PROXY_COUNT``, y los tres leen el mismo valor: si cada
    uno contara distinto, el log señalaría una IP y el límite castigaría otra.

    Con cero proxies se ignora ``X-Forwarded-For``: el cliente lo escribe a
    gusto, y confiar en él le permitiría elegir con qué IP figura.
    """
    if request is None:
        return None
    proxies = settings.NUM_PROXIES
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies > 0 and forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return _clean(hops[-min(proxies, len(hops))])
    return _clean(request.META.get("REMOTE_ADDR", ""))


def _clean(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def log_event(event: str, *, request: HttpRequest | None = None, **fields) -> None:
    """Escribe un evento de seguridad.

    ``event`` es un identificador corto y estable (``login_failed``,
    ``privacy_request``) que se puede filtrar con ``grep``. Los ``fields`` van
    tal cual: quien llama es responsable de no pasar nada secreto.
    """
    request = request or _current_request.get()
    user = getattr(request, "user", None)
    user_id = user.pk if user is not None and user.is_authenticated else None
    record = {
        "event": event,
        "user_id": fields.pop("user_id", user_id),
        "ip": client_ip(request),
        "path": request.path if request is not None else None,
        **fields,
    }
    logger.info(
        " ".join(f"{key}={_format(value)}" for key, value in record.items()),
        extra={"security": record},
    )


def _format(value) -> str:
    if value is None:
        return "-"
    text = str(value)
    # Un valor con espacios rompería el ``clave=valor``; uno con saltos de
    # línea permitiría inyectar un registro falso en el archivo.
    text = text.replace("\n", " ").replace("\r", " ")
    return f'"{text}"' if " " in text else text


class SecurityContextMiddleware:
    """Deja el request a mano de ``log_event`` y registra 401, 403 y 429.

    Va después de ``AuthenticationMiddleware`` para que la sesión ya esté
    resuelta. La autenticación por ``X-Session-Token`` de la API la resuelve DRF
    dentro de la vista, y su ``Request.user`` la copia sobre el request de
    Django: al volver la respuesta, ``request.user`` ya es el de la API.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        token = _current_request.set(request)
        try:
            response = self.get_response(request)
            if response.status_code in LOGGED_STATUSES:
                log_event(
                    f"http_{response.status_code}",
                    request=request,
                    method=request.method,
                )
            return response
        finally:
            _current_request.reset(token)


#: Los códigos de error de allauth que significan "frenado por límite".
LOCKOUT_ERROR_CODES = frozenset({"too_many_login_attempts"})


class HeadlessLockoutMiddleware:
    """Devuelve ``429`` cuando allauth headless frena un login por intentos.

    allauth aplica el límite de intentos fallidos (``login_failed``) como un
    error de validación del formulario, y la API headless lo contesta con un
    ``400`` igual al de una contraseña mal escrita. Los demás límites de
    allauth ya responden ``429``; este tiene que responder lo mismo para que
    los clientes muestren "esperá unos minutos" en vez de "revisá tus datos".

    El cuerpo no se toca: sigue llevando el código ``too_many_login_attempts``
    y el mensaje genérico de allauth, que no dice si la cuenta existe.

    Lo mismo con el reenvío de la confirmación de correo (``PUT
    /account/email``): allauth contesta ``403`` sin cuerpo cuando no lo envió,
    y con la verificación por enlace la única razón para no enviarlo es el
    límite ``confirm_email``.

    Va **después** de ``SecurityContextMiddleware`` en ``MIDDLEWARE``, así el
    registro ve el ``429`` ya corregido.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not request.path.startswith("/_allauth/"):
            return response
        if response.status_code == 400 and _has_lockout_error(response):  # noqa: PLR2004
            response.status_code = 429
            log_event("login_locked", request=request)
        elif (
            response.status_code == 403  # noqa: PLR2004
            and request.method == "PUT"
            and request.path.endswith("/account/email")
        ):
            response.status_code = 429
            log_event("email_confirmation_limited", request=request)
        return response


def _has_lockout_error(response: HttpResponse) -> bool:
    if "json" not in response.get("Content-Type", ""):
        return False
    try:
        payload = json.loads(response.content)
    except ValueError:
        return False
    errors = payload.get("errors", []) if isinstance(payload, dict) else []
    return any(
        isinstance(error, dict) and error.get("code") in LOCKOUT_ERROR_CODES
        for error in errors
    )


#: Rutas que llevan la política de contenido de ``SECURE_CSP`` (C-05), además
#: del admin, cuya ruta sale de ``ADMIN_URL``.
CSP_PATHS = ("/api/docs/",)


class AdminAndDocsCSPMiddleware(ContentSecurityPolicyMiddleware):
    """``ContentSecurityPolicyMiddleware`` de Django, acotado al admin y a Swagger.

    Son las únicas pantallas HTML de administración que sirve el backend. El
    resto no la lleva: la API responde JSON, y la vista previa de un reporte
    compartido (US-030) redirige con un script inline que la política
    bloquearía. Ampliarla a otra página es sumar su prefijo a ``CSP_PATHS``.
    """

    def process_response(self, request, response):
        prefixes = (f"/{settings.ADMIN_URL}", *CSP_PATHS)
        if not request.path.startswith(prefixes):
            return response
        return super().process_response(request, response)
