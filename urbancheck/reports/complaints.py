"""El acto de denunciar un reporte (US-021).

Cubre **solo** el registro: quién puede denunciar, qué, y a quién le llega. La
resolución no vive acá: las de contenido las resuelve el agente municipal
(US-049) y las de dato personal el administrador de la plataforma (US-043,
``privacy.py``).

Dos reglas que conviene no perder de vista:

- **Las dos partes se enteran, pero no una de la otra.** Quien denuncia recibe
  el acuse entre sus avisos. El autor recibe un aviso de que su reporte fue
  denunciado, sin el denunciante ni el motivo, y **uno solo** mientras haya
  denuncias de contenido pendientes: uno por denuncia le diría cuántas hay, que
  es justo lo que el escenario 9 reserva. Con el motivo de dato personal al
  autor le avisa el circuito de US-043, que además le explica el ocultamiento.
- **Registrar una denuncia no toca el reporte.** No hay transición de estado ni
  cambio de visibilidad, por más denuncias que se acumulen: un umbral de
  denuncias es mucho más barato de explotar que el de me gusta de US-040 —tres
  cuentas nuevas tumbarían cualquier reclamo incómodo—. La única excepción es
  el motivo de dato personal, y la produce ``privacy.py``, no este módulo.
- **El destinatario sale del catálogo** (``ReportComplaint.REASON_RECIPIENTS``),
  no de condicionales: acá solo se distingue si el motivo pertenece al circuito
  de US-043, que tiene sus propias reglas de duplicado y de imagen.
"""

from __future__ import annotations

from django.db import IntegrityError
from django.db import transaction

from urbancheck.common.security import log_event
from urbancheck.notifications.services import notify_complaint_received
from urbancheck.notifications.services import notify_report_reported

from .models import Report
from .models import ReportComplaint
from .privacy import ComplaintError
from .privacy import DuplicateComplaintError
from .privacy import describe_window
from .privacy import request_personal_data_review


class OwnReportError(ComplaintError):
    """El autor no denuncia su propio reporte (escenario 7)."""


class ReportNotPublicError(ComplaintError):
    """El reporte ya no es visible públicamente (escenario 8)."""


def reason_catalog() -> list[dict[str, str]]:
    """Los motivos que se ofrecen al denunciar, cada uno con su destinatario."""
    return [
        {
            "value": reason.value,
            "label": reason.label,
            "recipient": ReportComplaint.REASON_RECIPIENTS[reason].value,
        }
        for reason in ReportComplaint.Reason
    ]


def file_complaint(
    *,
    report: Report,
    reporter,
    reason: str,
    comment: str = "",
) -> ReportComplaint:
    """Registra la denuncia de ``reporter`` sobre ``report``."""
    if report.author_id == reporter.pk:
        msg = "No podés denunciar tu propio reporte."
        raise OwnReportError(msg)
    # Cancelado y Archivado ya salieron del feed y del mapa; uno retirado por
    # protección de datos, también y para siempre. No queda nada que revisar.
    if (
        report.status in Report.INACTIVE_PUBLIC_STATUSES
        or report.photo_removed_at is not None
    ):
        msg = "Este reporte ya no está publicado."
        raise ReportNotPublicError(msg)

    if reason in ReportComplaint.PLATFORM_REASONS:
        # Oculta el reporte y avisa al autor: es el circuito de US-043 entero,
        # con su propia regla de duplicado (por imagen y mientras esté en curso).
        complaint = request_personal_data_review(
            report=report,
            reporter=reporter,
            comment=comment,
        )
    else:
        complaint = _file_content_complaint(report, reporter, reason, comment)
    notify_complaint_received(complaint, message=confirmation_for(complaint))
    return complaint


def _file_content_complaint(report, reporter, reason, comment) -> ReportComplaint:
    # Se mira antes de crear: si ya tenía una denuncia de contenido en curso, el
    # autor ya recibió el aviso.
    already_reported = (
        ReportComplaint.objects.for_municipal_review()
        .filter(report=report, status=ReportComplaint.Status.PENDIENTE)
        .exists()
    )
    try:
        # El savepoint deja la transacción de la petición usable cuando la
        # restricción única rechaza la fila; es ella la que decide el duplicado,
        # sin una consulta previa que otra petición pueda adelantar.
        with transaction.atomic():
            complaint = ReportComplaint.objects.create(
                report=report,
                reporter=reporter,
                reason=reason,
                comment=comment,
            )
    except IntegrityError as error:
        msg = "Ya denunciaste este reporte por ese motivo."
        raise DuplicateComplaintError(msg) from error
    log_event(
        "complaint_filed",
        user_id=reporter.pk,
        report=report.pk,
        complaint=complaint.pk,
        reason=reason,
    )
    if not already_reported:
        notify_report_reported(report)
    return complaint


def confirmation_for(complaint: ReportComplaint) -> str:
    """Lo que se le confirma al vecino: quién la revisa y, si hay, en qué plazo."""
    if complaint.recipient == ReportComplaint.Recipient.ADMIN_PLATAFORMA:
        return (
            "Recibimos tu denuncia. Ocultamos el reporte mientras revisamos la "
            f"imagen, y la revisión se hace dentro de las {describe_window()}."
        )
    return "Recibimos tu denuncia. La va a revisar el municipio del reporte."
