"""La vista previa de un enlace compartido en redes (US-030).

WhatsApp, Facebook, X y compañía arman la tarjeta del enlace leyendo las
etiquetas Open Graph del HTML **que manda el servidor**: no ejecutan JavaScript.
La página pública del reporte es del panel, una SPA, y a un bot le devolvería
siempre el mismo ``index.html`` sin nada del reporte.

Por eso ``/r/<token>`` lo responde Django con un HTML mínimo: las etiquetas OG
del reporte —título, descripción y la foto **difuminada**— y una redirección
por JavaScript a la página del panel (``PUBLIC_REPORT_PAGE_URL``). El bot no
ejecuta la redirección y se queda con las etiquetas; una persona llega a la
página completa sin notarlo. Con la app instalada, ``/r/*`` ni siquiera llega
acá: lo abre la app (Universal Links y App Links).

Muestra lo mismo que el endpoint público: lo decide la función única de
visibilidad. Un reporte que ya no es público no filtra nada en la vista previa.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import Report

DESCRIPTION_LENGTH = 180
SITE_NAME = "UrbanCheck"


def _truncate(text: str, length: int = DESCRIPTION_LENGTH) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def page_url_for(token) -> str:
    return settings.PUBLIC_REPORT_PAGE_URL.format(token=token)


@require_GET
def shared_report_preview(request, token):
    report = (
        Report.objects.publicly_visible()
        .select_related("municipality")
        .filter(share_token=token)
        .first()
    )
    context = {"site_name": SITE_NAME, "page_url": page_url_for(token)}
    if report is None:
        context.update(
            title=f"Este reporte ya no está disponible · {SITE_NAME}",
            description="Reportá problemas de tu barrio y seguí su resolución "
            "junto al municipio.",
            image=None,
        )
        return render(request, "reports/share_preview.html", context, status=404)

    city = report.municipality.city
    likes = report.likes.count()
    support = "1 vecino lo apoya" if likes == 1 else f"{likes} vecinos lo apoyan"
    context.update(
        title=f"{report.get_category_display()} en {city} · Reporte "
        f"#{report.number or report.pk}",
        description=_truncate(
            f"{report.description} — {report.get_status_display()}. {support}.",
        ),
        image=request.build_absolute_uri(report.photo.url) if report.photo else None,
        url=request.build_absolute_uri(),
    )
    return render(request, "reports/share_preview.html", context)
