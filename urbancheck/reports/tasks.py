"""Tareas asíncronas de la app de reportes."""

import logging

from django.conf import settings

from config.celery_app import app

from .archival import run_archival
from .comparison import mark_unavailable
from .comparison import run_comparison
from .resolution import run_confirmation
from .vision import TransientVisionError
from .vision import VisionError

logger = logging.getLogger(__name__)

#: Espera base entre reintentos de la comparación; se duplica en cada intento.
COMPARISON_RETRY_BASE_SECONDS = 30


@app.task()
def archive_stale_reports() -> dict[str, int]:
    """Verificación del archivado por inactividad (US-031), cada 15 minutos.

    La frecuencia la fija ``CELERY_BEAT_SCHEDULE``: corre cada quince minutos y
    no una vez por día, para que un plazo bajado a minutos se pueda demostrar.

    Delega en ``archival.run_archival``, igual que el comando de management: la
    política del plazo vive en un solo lugar.
    """
    return run_archival()


@app.task()
def confirm_resolved_reports() -> dict[str, int]:
    """Verificación de la ventana de objeción de US-047.

    Delega en ``resolution.run_confirmation``, igual que el comando de
    management: la política del plazo vive en un solo lugar.
    """
    return run_confirmation()


@app.task(bind=True)
def compare_resolution(self, evidence_id: int) -> None:
    """Compara el antes y el después de un cierre (US-015).

    Reintenta solo los fallos transitorios, y cuántas veces lo dice la
    configuración. Cualquier otro final sin veredicto —reintentos agotados,
    respuesta fuera de formato, un error inesperado— deja la comparación como
    no disponible: nunca pendiente para siempre, y nunca con efecto sobre el
    reporte.
    """
    max_retries = settings.RESOLUTION_COMPARISON_MAX_RETRIES
    try:
        run_comparison(evidence_id)
    except TransientVisionError as exc:
        if self.request.retries >= max_retries:
            mark_unavailable(evidence_id, exc.code)
            return
        raise self.retry(
            exc=exc,
            countdown=COMPARISON_RETRY_BASE_SECONDS * 2**self.request.retries,
            max_retries=max_retries,
        ) from exc
    except VisionError as exc:
        mark_unavailable(evidence_id, exc.code)
    except Exception:
        logger.exception("Falló la comparación de la evidencia %s.", evidence_id)
        mark_unavailable(evidence_id, "unexpected_error")
