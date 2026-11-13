"""Revisión de imágenes por dato personal visible (US-043, RN-12, Ley 25.326).

Un ciudadano denuncia una foto publicada en la que el difuminado automático de
US-041 no detectó un rostro o una patente. Tres reglas definen el circuito, y
las tres viven acá:

- **Oculta de inmediato.** Una sola solicitud retiene el reporte fuera de las
  vistas públicas, sin umbral. No hay código que lo haga: lo deduce
  ``on_privacy_hold()`` de que exista una solicitud pendiente, y deja de
  ocultarlo cuando ninguna lo está.
- **Resuelven el administrador de la plataforma y el agente municipal** de la
  municipalidad del reporte. US-043 la dejaba solo al admin; el usuario sumó al
  agente el 21/10. El parámetro ``admin`` de las funciones es quien decide,
  sea cual sea su rol.
- **La eliminación es física.** Un borrado lógico que conserva el archivo no
  satisface la RN-12.

Se resuelve **por imagen, no por solicitud**: eliminar o desestimar cierra todas
las solicitudes pendientes sobre ese mismo archivo. Si no, el reporte seguiría
oculto por las solicitudes de otros vecinos sobre algo que ya se decidió.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from urbancheck.common.security import log_event
from urbancheck.notifications.services import notify_complaint_resolved
from urbancheck.notifications.services import notify_image_removed
from urbancheck.notifications.services import notify_report_restored
from urbancheck.notifications.services import notify_report_under_review
from urbancheck.users.models import User

from .models import Report
from .models import ReportComplaint
from .models import ResolutionAppeal
from .models import ResolutionEvidence
from .models import on_privacy_hold


class ComplaintError(Exception):
    """Una solicitud que no se puede registrar o resolver."""


class DuplicateComplaintError(ComplaintError):
    """El mismo usuario ya tiene una solicitud en curso sobre esa imagen."""


class NoImageError(ComplaintError):
    """La imagen denunciada ya no está: se retiró, o nunca la hubo."""


class ComplaintAlreadyResolvedError(ComplaintError):
    """Otra decisión llegó antes: la solicitud ya no está pendiente."""


def review_window() -> timedelta:
    """El plazo comprometido por la RN-12. Se lee en cada consulta."""
    return timedelta(minutes=settings.PERSONAL_DATA_REVIEW_MINUTES)


def deadline_for(complaint: ReportComplaint) -> datetime:
    """Hasta cuándo hay para resolverla: desde la **recepción**, nunca desde la
    última modificación (notas de implementación de US-043)."""
    return complaint.created_at + review_window()


def describe_window() -> str:
    """El plazo en palabras, para la confirmación que recibe el ciudadano.

    Sale de la configuración y no de un texto fijo: si la demostración baja el
    plazo a minutos, la confirmación no puede seguir prometiendo 24 horas.
    """
    minutes = settings.PERSONAL_DATA_REVIEW_MINUTES
    if minutes % 60:
        return f"{minutes} minuto{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    return f"{hours} hora{'s' if hours != 1 else ''}"


def request_personal_data_review(
    *,
    report: Report,
    reporter,
    evidence: ResolutionEvidence | None = None,
    appeal: ResolutionAppeal | None = None,
    comment: str = "",
) -> ReportComplaint:
    """Registra la solicitud; el reporte queda oculto en el mismo commit.

    Cualquier usuario puede presentarla, sea o no el autor del reporte y sea o
    no la persona que aparece (escenario 3): la RN-12 habilita a cualquiera.
    La imagen es la del reporte, la de un cierre (``evidence``) o la de una
    apelación (``appeal``), nunca dos a la vez.
    """
    if evidence is not None and appeal is not None:
        msg = "Una solicitud señala una sola imagen."
        raise ValueError(msg)
    target = evidence or appeal or report
    image_name = target.photo.name
    if not image_name:
        msg = "La imagen ya fue retirada."
        raise NoImageError(msg)

    pending = ReportComplaint.objects.filter(
        report=report,
        resolution_evidence=evidence,
        resolution_appeal=appeal,
        reporter=reporter,
        reason=ReportComplaint.Reason.DATO_PERSONAL,
        status=ReportComplaint.Status.PENDIENTE,
    )
    if pending.exists():
        msg = "Ya hay una solicitud en curso sobre esta imagen."
        raise DuplicateComplaintError(msg)
    # Se mira antes de crear: si ya estaba oculto por otra denuncia, el autor ya
    # recibió el aviso y no tiene por qué recibir uno por cada vecino.
    was_hidden = Report.objects.filter(pk=report.pk).filter(on_privacy_hold()).exists()
    try:
        # El savepoint deja la transacción de la petición usable si la carrera
        # la gana otra petición del mismo usuario: la restricción única es la
        # que tiene la última palabra, la consulta de arriba solo da el mensaje.
        with transaction.atomic():
            complaint = ReportComplaint.objects.create(
                report=report,
                resolution_evidence=evidence,
                resolution_appeal=appeal,
                image_name=image_name,
                reporter=reporter,
                reason=ReportComplaint.Reason.DATO_PERSONAL,
                comment=comment,
            )
    except IntegrityError as error:
        msg = "Ya hay una solicitud en curso sobre esta imagen."
        raise DuplicateComplaintError(msg) from error
    # Antiabuso (US-043): ocultar un reporte cuesta una sola solicitud, así que
    # cada una queda con quién y desde dónde la presentó.
    log_event(
        "privacy_request",
        user_id=reporter.pk,
        report=report.pk,
        complaint=complaint.pk,
        evidence=evidence.pk if evidence is not None else None,
        appeal=appeal.pk if appeal is not None else None,
    )
    # Si lo denunció el propio autor, ya sabe lo que pasa: no hay que avisarle.
    if not was_hidden and reporter.pk != report.author_id:
        notify_report_under_review(report)
    return complaint


def remove_image(complaint: ReportComplaint, *, admin) -> ReportComplaint:
    """Borra el archivo denunciado del almacenamiento (escenarios 5 y 11).

    Si es la foto **del reporte**, el reporte queda retirado para siempre: un
    reporte sin foto no se vuelve a publicar (decisión de producto posterior a
    la historia, que pedía republicarlo sin imagen). Lo marca
    ``photo_removed_at``, que ``publicly_visible`` excluye. La fila no se borra:
    el registro de cumplimiento de la RN-12 cuelga de ella, y el autor y el
    municipio lo siguen viendo.

    Si es la foto de **un cierre** (escenario 11) o de **una apelación**
    (escenario 1), el reporte conserva la suya, su estado, el parte de trabajo
    y el motivo de la apelación, y vuelve a verse si nada más lo retiene.

    **El archivo se borra dentro de la transacción y al final**, no en un
    ``on_commit``. Son dos órdenes con dos fallas posibles, y se elige la que no
    viola la RN-12: si el borrado falla, la transacción se revierte, el
    administrador ve el error y la solicitud sigue pendiente —y el reporte
    oculto—. Con ``on_commit``, un borrado caído dejaría la base diciendo
    "eliminada" con el archivo todavía servido, y nadie se enteraría. Si falla
    el commit después de borrar, el archivo ya no está y reintentar es inocuo:
    borrar lo que no existe no es un error.
    """
    with transaction.atomic():
        complaint = _lock_pending(complaint)
        now = timezone.now()
        evidence = complaint.resolution_evidence
        appeal = complaint.resolution_appeal
        if evidence is not None:
            target = ResolutionEvidence.objects.select_for_update().get(pk=evidence.pk)
        elif appeal is not None:
            target = ResolutionAppeal.objects.select_for_update().get(pk=appeal.pk)
        else:
            target = Report.objects.select_for_update().get(pk=complaint.report_id)
        storage = target.photo.storage
        # Si el autor reemplazó la foto mientras la solicitud esperaba, la que
        # se publica ya no es la denunciada: se borra el archivo denunciado y
        # la foto nueva queda donde está.
        if target.photo.name == complaint.image_name:
            target.photo = ""
            target.photo_removed_at = now
            target.save(update_fields=["photo", "photo_removed_at"])
        reporter_ids = _close_same_image(
            complaint,
            status=ReportComplaint.Status.IMAGEN_ELIMINADA,
            admin=admin,
            now=now,
        )
        storage.delete(complaint.image_name)

    log_event(
        "privacy_request_resolved",
        user_id=admin.pk,
        complaint=complaint.pk,
        report=complaint.report_id,
        decision="imagen_eliminada",
    )
    report = complaint.report
    notify_image_removed(
        report,
        removed=complaint.image_kind,
        still_hidden=Report.objects.filter(pk=report.pk)
        .filter(on_privacy_hold())
        .exists(),
    )
    notify_complaint_resolved(
        report,
        recipients=_reporters_to_notify(report, reporter_ids),
        image_removed=True,
        report_withdrawn=complaint.image_kind == "report",
    )
    complaint.refresh_from_db()
    return complaint


def dismiss(complaint: ReportComplaint, *, admin) -> ReportComplaint:
    """La imagen no expone ningún dato personal (escenario 6).

    La imagen queda intacta y el reporte recupera su visibilidad en el mismo
    commit. Al autor no se le avisa: nunca supo que estaba oculto más que por
    la marca de "en revisión", y que desaparezca es toda la noticia.
    """
    with transaction.atomic():
        complaint = _lock_pending(complaint)
        reporter_ids = _close_same_image(
            complaint,
            status=ReportComplaint.Status.DESESTIMADA,
            admin=admin,
            now=timezone.now(),
        )

    log_event(
        "privacy_request_resolved",
        user_id=admin.pk,
        complaint=complaint.pk,
        report=complaint.report_id,
        decision="desestimada",
    )
    report = complaint.report
    # Solo si de verdad volvió a publicarse: puede seguir oculto por una
    # denuncia sobre otra de sus imágenes.
    if not Report.objects.filter(pk=report.pk).filter(on_privacy_hold()).exists():
        notify_report_restored(report)
    notify_complaint_resolved(
        report,
        recipients=_reporters_to_notify(report, reporter_ids),
        image_removed=False,
    )
    complaint.refresh_from_db()
    return complaint


def _lock_pending(complaint: ReportComplaint) -> ReportComplaint:
    """Relee la solicitud bloqueada y verifica que siga pendiente.

    Dos administradores pueden abrir la misma solicitud a la vez. Sin el
    bloqueo, uno desestima y el otro elimina, y el registro termina diciendo
    las dos cosas.
    """
    # ``of=("self",)``: la evidencia viene por un join externo, que Postgres no
    # deja bloquear; el reporte o la evidencia se bloquean aparte, después.
    locked = (
        ReportComplaint.objects.select_for_update(of=("self",))
        .select_related("report", "resolution_evidence", "resolution_appeal")
        .get(pk=complaint.pk)
    )
    if not locked.is_pending:
        msg = "Esta solicitud ya fue resuelta."
        raise ComplaintAlreadyResolvedError(msg)
    return locked


def _close_same_image(complaint, *, status, admin, now) -> set[int]:
    """Resuelve con la misma decisión todas las pendientes sobre ese archivo.

    Devuelve quiénes las habían presentado: a todos se les cuenta el resultado.
    """
    pending = ReportComplaint.objects.filter(
        report_id=complaint.report_id,
        resolution_evidence_id=complaint.resolution_evidence_id,
        resolution_appeal_id=complaint.resolution_appeal_id,
        image_name=complaint.image_name,
        reason=complaint.reason,
        status=ReportComplaint.Status.PENDIENTE,
    )
    reporter_ids = set(pending.values_list("reporter_id", flat=True)) - {None}
    pending.update(status=status, resolved_at=now, resolved_by=admin)
    return reporter_ids


def _reporters_to_notify(report, reporter_ids: set[int]):
    """Quienes denunciaron, menos el autor: él ya recibe su propio aviso."""
    return User.objects.filter(pk__in=reporter_ids - {report.author_id})
