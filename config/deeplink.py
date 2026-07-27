"""Endpoints para Universal Links (iOS) y App Links (Android).

Permiten que un enlace https://urbancheck.com.ar/reset-password?key=... abra
directamente la app de UrbanCheck (sin pasar por el navegador) cuando está
instalada, y que caiga en la página web de reset de allauth como fallback
cuando la app no está presente.

Los identificadores (Apple App ID, package y huella del certificado Android)
se configuran por entorno; ver settings IOS_UNIVERSAL_LINK_APP_ID,
ANDROID_APP_PACKAGE y ANDROID_SHA256_CERT_FINGERPRINTS.
"""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET


@require_GET
def apple_app_site_association(request):
    """Sirve /.well-known/apple-app-site-association (iOS Universal Links).

    Debe responderse por HTTPS, sin redirecciones y con Content-Type JSON.
    """
    return JsonResponse(
        {
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appID": settings.IOS_UNIVERSAL_LINK_APP_ID,
                        "paths": ["/reset-password", "/reset-password/*"],
                    },
                ],
            },
        },
    )


@require_GET
def android_assetlinks(request):
    """Sirve /.well-known/assetlinks.json (Android App Links)."""
    return JsonResponse(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.ANDROID_APP_PACKAGE,
                    "sha256_cert_fingerprints": settings.ANDROID_SHA256_CERT_FINGERPRINTS,
                },
            },
        ],
        safe=False,
    )


@require_GET
def reset_password_web_fallback(request):
    """Fallback web del enlace de reset.

    Si la app está instalada, el SO intercepta /reset-password y abre la app
    antes de llegar acá. Si no, este endpoint redirige al formulario de reset
    de allauth para completar el cambio desde el navegador.
    """
    key = request.GET.get("key", "")
    return redirect(f"/accounts/password/reset/key/{key}/")
