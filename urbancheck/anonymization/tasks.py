"""La tarea que difumina una foto fuera del request (US-042).

Espeja a ``reports.tasks.compare_resolution``: reintenta solo lo transitorio,
cuántas veces lo dice la configuración, y **toda** rama termina en ``procesada``
o en ``fallida``. Una foto que se queda en ``pendiente`` para siempre es un
reporte invisible para siempre, que es la forma silenciosa de perder un reclamo.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from config.celery_app import app

from .models import PendingPhotoMixin
from .models import PhotoStatus
from .pipeline import mark_failed
from .pipeline import run_anonymization
from .service import PermanentAnonymizationError
from .service import TransientAnonymizationError

logger = logging.getLogger(__name__)


@app.task(bind=True)
def anonymize_photo(self, label: str, pk: int) -> None:
    """Difumina la foto pendiente de ``label`` #``pk`` y la publica."""
    max_retries = settings.ANONYMIZATION_MAX_RETRIES
    base = settings.ANONYMIZATION_RETRY_BASE_SECONDS
    try:
        run_anonymization(label, pk)
    except TransientAnonymizationError as exc:
        # Falló el detector, no la imagen: el mismo archivo puede salir bien.
        if self.request.retries >= max_retries:
            mark_failed(label, pk, exc.code)
            return
        raise self.retry(
            exc=exc,
            countdown=base * 2**self.request.retries,
            max_retries=max_retries,
        ) from exc
    except PermanentAnonymizationError as exc:
        # Reintentar un archivo que no se puede abrir da siempre lo mismo: se
        # falla de una y el ciudadano se entera ahora, no dentro de una hora.
        mark_failed(label, pk, exc.code)
    except FileNotFoundError:
        mark_failed(label, pk, "source_missing")
    except ObjectDoesNotExist:
        # El autor borró el reporte mientras se procesaba. No es un error.
        logger.info("Ya no existe %s #%s; no hay foto que procesar.", label, pk)
    except Exception:
        logger.exception("Falló el difuminado de %s #%s.", label, pk)
        mark_failed(label, pk, "unexpected_error")


@app.task()
def requeue_stale_pending_photos() -> dict[str, int]:
    """Rescata las fotos que quedaron en cola y nadie procesó.

    Un Redis que se reinicia o un worker que muere con el mensaje en la mano
    dejan la fila en ``pendiente`` sin que haya nadie por venir a buscarla, y el
    reporte queda invisible sin ningún camino de recuperación: no falló, así que
    su autor tampoco recibe el aviso de US-042. Esta verificación periódica es
    el único seguro contra esa pérdida silenciosa, y es barata porque el filtro
    es sobre una columna indexada por estado y en la práctica no devuelve nada.

    Es idempotente: reencolar algo que sí se estaba procesando termina en un
    ``run_anonymization`` que ve la fila ya procesada y vuelve enseguida.
    """
    cutoff = timezone.now() - timedelta(
        minutes=settings.ANONYMIZATION_STALE_MINUTES,
    )
    requeued = 0
    for model in apps.get_models():
        if not issubclass(model, PendingPhotoMixin):
            continue
        # `_default_manager` y no `objects`: el modelo sale de `get_models()`,
        # así que acá es un `type[Model]` cualquiera.
        stale = model._default_manager.filter(  # noqa: SLF001
            photo_status=PhotoStatus.PENDIENTE,
        ).exclude(photo_pending="").filter(photo_queued_at__lte=cutoff)
        for pk in stale.values_list("pk", flat=True):
            anonymize_photo.delay(model._meta.label_lower, pk)  # noqa: SLF001
            requeued += 1
    if requeued:
        logger.warning("Se reencolaron %d fotos que quedaron sin procesar.", requeued)
    return {"requeued": requeued}
