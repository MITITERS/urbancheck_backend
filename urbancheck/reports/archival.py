"""Archivado automático de reportes sin validar (US-031).

Un reporte que nadie confirma en terreno y que a nadie le interesa —ni un me
gusta ni un comentario en medio año— dejó de ser una problemática urbana
vigente. El mapa y el feed tienen que reflejar lo que pasa hoy, así que el
sistema lo archiva solo.

Toda la política vive en este módulo: el plazo, qué cuenta como interacción y
cuándo se avisa. El comando de management y la tarea de Celery son dos formas de
dispararlo, no dos copias de la regla.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import DateTimeField
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.db.models.functions import Greatest
from django.utils import timezone

from urbancheck.notifications.services import notify_upcoming_archival

from .models import Report
from .services import TransitionError
from .services import apply_transition
from .state_machine import Actor


def inactivity_days() -> int:
    """Días sin interacción tras los cuales un reporte se archiva solo.

    Se lee de configuración **en cada evaluación** y no se captura al importar:
    cambiar el plazo tiene que alcanzar con editar el entorno y reiniciar, sin
    tocar código. Una constante de módulo seguiría sirviendo el número viejo.
    """
    return settings.ARCHIVAL_INACTIVITY_DAYS


#: Cuántos días antes del plazo se le avisa al autor. El aviso existe para que
#: el vecino tenga margen de conseguir la interacción que le falta, no para
#: notificarle un hecho consumado.
WARNING_DAYS_BEFORE = 7

#: Operación de la máquina de estados que ejecuta este módulo.
ARCHIVE_OPERATION = "archivar_por_inactividad"


def _with_last_interaction(queryset):
    """Anota la fecha de la última señal de vida del reporte.

    Es el máximo entre su creación, su comentario más reciente y su me gusta más
    reciente. Se calcula en la base y no en Python porque después se filtra por
    ella: traer todos los reportes pendientes para descartarlos acá no escala.

    ``Coalesce`` contra ``created_at`` cubre los dos casos sin interacciones y,
    de paso, los me gusta anteriores a que ``Like`` tuviera fecha.
    """
    return queryset.annotate(
        last_comment_at=Max("comments__created_at"),
        last_like_at=Max("likes__created_at"),
    ).annotate(
        last_interaction_at=Greatest(
            "created_at",
            Coalesce("last_comment_at", "created_at"),
            Coalesce("last_like_at", "created_at"),
            output_field=DateTimeField(),
        ),
    )


def _pending(queryset=None):
    """Los candidatos: únicamente reportes pendientes de validación.

    Un reporte validado ya entró en la cola del municipio y su archivado es una
    decisión de gestión (US-013), no una consecuencia del desinterés.
    """
    base = Report.objects.all() if queryset is None else queryset
    return _with_last_interaction(
        base.filter(status=Report.Status.PENDIENTE_VALIDACION),
    )


def reports_due_for_archival(now=None, queryset=None):
    """Reportes que ya cumplieron el plazo completo sin interacción."""
    now = now or timezone.now()
    deadline = now - timedelta(days=inactivity_days())
    return _pending(queryset).filter(last_interaction_at__lte=deadline)


def reports_due_for_warning(now=None, queryset=None):
    """Reportes a los que les faltan ``WARNING_DAYS_BEFORE`` días.

    Se excluyen los ya avisados: la verificación corre todos los días y sin esa
    condición el vecino recibiría el mismo aviso siete veces. Si el reporte
    recibe una interacción, el reloj se reinicia y el aviso vuelve a habilitarse
    porque ``archival_warning_sent_at`` queda por detrás de la ventana nueva.
    """
    now = now or timezone.now()
    window = inactivity_days()
    warning_from = now - timedelta(days=window - WARNING_DAYS_BEFORE)
    deadline = now - timedelta(days=window)
    return _pending(queryset).filter(
        last_interaction_at__lte=warning_from,
        last_interaction_at__gt=deadline,
    )


def archives_on(report, now=None):
    """Cuándo se archivaría el reporte si nadie interactúa.

    Necesita la anotación de ``_with_last_interaction``; sin ella cae en la
    fecha de creación, que es el valor correcto para un reporte sin actividad.
    """
    last = getattr(report, "last_interaction_at", None) or report.created_at
    return last + timedelta(days=inactivity_days())


def run_archival(now=None) -> dict[str, int]:
    """Ejecuta la verificación periódica completa.

    Primero los avisos y después los archivados, para que un reporte que cruza
    las dos ventanas en la misma corrida —porque la verificación no corrió por
    unos días— se archive en lugar de recibir un aviso que ya no sirve.

    Devuelve las dos cifras para que el comando pueda informarlas.
    """
    now = now or timezone.now()
    warned = _send_warnings(now)
    archived = _archive(now)
    return {"warned": warned, "archived": archived}


def _send_warnings(now) -> int:
    warned = 0
    for report in reports_due_for_warning(now).select_related("author"):
        if (
            report.archival_warning_sent_at is not None
            and report.archival_warning_sent_at >= report.last_interaction_at
        ):
            continue
        notify_upcoming_archival(report, archives_on=archives_on(report, now))
        report.archival_warning_sent_at = now
        report.save(update_fields=["archival_warning_sent_at"])
        warned += 1
    return warned


def _archive(now) -> int:
    archived = 0
    for report in reports_due_for_archival(now):
        try:
            apply_transition(
                report,
                ARCHIVE_OPERATION,
                actor=Actor.SYSTEM,
                # Sin responsable humano: así queda asentado en el historial que
                # esto lo decidió el sistema y no una persona.
                changed_by=None,
            )
        except TransitionError:
            # Alguien lo movió entre la consulta y la transición. No es un
            # error: el reporte dejó de ser candidato, que es justo lo que se
            # quería.
            continue
        archived += 1
    return archived
