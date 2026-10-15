"""Qué le pasa a una foto entre que se sube y que se publica (US-042).

El circuito es siempre el mismo, venga del alta de un reporte, del reemplazo de
la foto, del cierre del operario o de una apelación: la original queda en el
storage privado con el estado en ``pendiente``, una tarea la difumina y escribe
``photo``, y la original se borra. Si no se puede procesar tras agotar los
reintentos, el estado pasa a ``fallida``, la original se borra igual y el
contenido no se publica nunca. No hay vía degradada.

La instancia se identifica por ``label`` (``"reports.report"``) y ``pk``, los
dos serializables a JSON, que es lo que el broker transporta. Pasar la
instancia entera obligaría a un serializador que sabe de objetos Django y
mandaría al worker una copia posiblemente vieja.

Los efectos que dependen del modelo —encadenar la comparación de US-015,
avisarle a quien corresponda— no viven acá: se registran como hooks, para que
esta app no tenga que importar ``reports``.
"""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from .models import PhotoStatus
from .service import AnonymizationError
from .service import anonymize

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model

logger = logging.getLogger(__name__)

#: Efectos posteriores al procesamiento, por ``label`` del modelo. Los registra
#: la app dueña del modelo (ver ``urbancheck/reports/apps.py``); un modelo sin
#: hooks simplemente no tiene nada más que hacer.
_ON_SUCCESS: dict[str, Callable[[Model], None]] = {}
_ON_FAILURE: dict[str, Callable[[Model, str], None]] = {}


def register_hooks(
    label: str,
    *,
    on_success: Callable[[Model], None] | None = None,
    on_failure: Callable[[Model, str], None] | None = None,
) -> None:
    if on_success is not None:
        _ON_SUCCESS[label] = on_success
    if on_failure is not None:
        _ON_FAILURE[label] = on_failure


def label_of(instance) -> str:
    return instance._meta.label_lower  # noqa: SLF001


def schedule_anonymization(instance) -> None:
    """Encola el difuminado de ``instance`` para cuando la transacción cierre.

    ``on_commit`` no es una precaución sino un requisito: con
    ``ATOMIC_REQUESTS = True`` todo el request corre en una transacción, y un
    worker que toma el mensaje antes del commit no encuentra la fila.
    """
    # Import local: ``tasks`` importa este módulo.
    from .tasks import anonymize_photo  # noqa: PLC0415

    instance.photo_queued_at = timezone.now()
    instance.save(update_fields=["photo_queued_at"])
    transaction.on_commit(
        partial(anonymize_photo.delay, label_of(instance), instance.pk),
    )


def restart_anonymization(instance) -> None:
    """Vuelve a poner en cola una foto que se reemplazó o que hay que reintentar.

    Se usa cuando el autor cambia la foto de su reporte (US-018) y cuando
    vuelve a cargarla después de un fallo definitivo. La foto anterior ya
    publicada se borra: mientras la nueva se procesa el reporte no es visible,
    y dejar la vieja colgada solo confundiría al autor, que ya la reemplazó.
    """
    if instance.photo:
        instance.photo.delete(save=False)
    instance.photo_status = PhotoStatus.PENDIENTE
    instance.photo_attempts = 0
    instance.photo_failed_at = None
    instance.save(
        update_fields=["photo", "photo_status", "photo_attempts", "photo_failed_at"],
    )
    schedule_anonymization(instance)


def run_anonymization(label: str, pk: int) -> None:
    """Difumina la foto pendiente de una instancia y la publica.

    Idempotente a propósito: si la fila ya está procesada no hace nada. Un
    broker puede entregar el mismo mensaje dos veces, y la segunda vez la
    original ya no está.
    """
    model = apps.get_model(label)
    with transaction.atomic():
        instance = model.objects.select_for_update().get(pk=pk)
        if instance.photo_status == PhotoStatus.PROCESADA:
            return
        if not instance.photo_pending:
            # Sin original no hay nada que procesar, y el estado no puede
            # quedarse en `pendiente` para siempre.
            msg = "No quedó foto pendiente que procesar."
            raise FileNotFoundError(msg)

        pending_name = instance.photo_pending.name
        with instance.photo_pending.open("rb") as file:
            content = anonymize(file)

        instance.photo_attempts += 1
        instance.photo_status = PhotoStatus.PROCESADA
        instance.photo_failed_at = None
        # La referencia a la original se suelta acá, no cuando el archivo se
        # borra: dejarla apuntando a algo que ya no existe es una referencia
        # rota que el día de mañana alguien intenta abrir.
        instance.photo_pending = ""
        # `save=False`: se escribe todo junto abajo, en un solo UPDATE.
        instance.photo.save(content.name, content, save=False)
        instance.save(
            update_fields=[
                "photo",
                "photo_pending",
                "photo_status",
                "photo_attempts",
                "photo_failed_at",
            ],
        )
        # El borrado de la original va después del commit: si la transacción se
        # deshace, el archivo tiene que seguir estando para el reintento.
        transaction.on_commit(partial(_discard_pending, label, pk, pending_name))

    hook = _ON_SUCCESS.get(label)
    if hook is not None:
        hook(instance)


def mark_failed(label: str, pk: int, code: str) -> None:
    """Da la foto por perdida: no se publica y el autor se entera.

    La original se borra también acá. Conservarla "por las dudas" dejaría en
    disco justo lo que la historia no quiere que exista: una foto sin difuminar
    que nadie va a procesar.
    """
    model = apps.get_model(label)
    with transaction.atomic():
        instance = model.objects.select_for_update().get(pk=pk)
        if instance.photo_status == PhotoStatus.PROCESADA:
            # Llegó tarde: otro intento ya la publicó.
            return
        pending_name = instance.photo_pending.name
        instance.photo_status = PhotoStatus.FALLIDA
        instance.photo_failed_at = timezone.now()
        instance.photo_pending = ""
        instance.save(
            update_fields=["photo_status", "photo_failed_at", "photo_pending"],
        )
        if pending_name:
            transaction.on_commit(partial(_discard_pending, label, pk, pending_name))

    # Sin el nombre del archivo: el log no puede señalar la original (mismo
    # criterio que el servicio). `code` es lo que sirve para diagnosticar.
    logger.warning(
        "No se pudo anonimizar la foto de %s #%s tras %d intentos (%s).",
        label,
        pk,
        instance.photo_attempts,
        code,
    )
    hook = _ON_FAILURE.get(label)
    if hook is not None:
        hook(instance, code)


def legacy_photos(model):
    """Fotos publicadas que nunca pasaron por el servicio (US-042, escenario 9).

    Son las que la migración ``reports/0012`` marcó como ``procesada`` sin
    procesarlas: el circuito suma un intento a cada foto que difumina, así que
    una publicada con cero intentos es una que llegó antes de US-041.
    """
    return model.objects.filter(
        photo_status=PhotoStatus.PROCESADA,
        photo_attempts=0,
    ).exclude(photo="")


def reprocess_legacy_photo(label: str, pk: int) -> str:
    """Difumina una foto ya publicada que nunca pasó por el servicio.

    Devuelve ``"processed"``, ``"failed"``, ``"missing"`` o ``"skipped"``. La
    nueva versión reemplaza a la vieja y la vieja se borra después del commit.
    Si el servicio no puede con ella, la foto **se retira**: una foto sin
    difuminar no queda publicada "por las dudas", que es la misma regla del
    fallo definitivo de ``mark_failed``. El autor se entera por el mismo aviso.

    Es idempotente: una foto ya reprocesada tiene un intento y no se vuelve a
    tocar.
    """
    model = apps.get_model(label)
    with transaction.atomic():
        instance = model.objects.select_for_update().get(pk=pk)
        if not instance.photo or instance.photo_attempts:
            return "skipped"
        old_name = instance.photo.name
        storage = instance.photo.storage
        if not storage.exists(old_name):
            return "missing"
        code = None
        try:
            with instance.photo.open("rb") as file:
                content = anonymize(file)
        except AnonymizationError as error:
            code = error.code
            instance.photo = ""
            instance.photo_status = PhotoStatus.FALLIDA
            instance.photo_failed_at = timezone.now()
            instance.save(
                update_fields=["photo", "photo_status", "photo_failed_at"],
            )
        else:
            instance.photo_attempts = 1
            instance.photo.save(content.name, content, save=False)
            instance.save(update_fields=["photo", "photo_attempts"])
        transaction.on_commit(partial(_discard_published, storage, old_name))

    if code is None:
        return "processed"
    logger.warning(
        "Se retiró la foto preexistente de %s #%s: no se pudo anonimizar (%s).",
        label,
        pk,
        code,
    )
    hook = _ON_FAILURE.get(label)
    if hook is not None:
        hook(instance, code)
    return "failed"


def _discard_published(storage, name: str) -> None:
    try:
        storage.delete(name)
    except OSError:
        logger.exception("Quedó sin borrar una foto reemplazada.")


def _discard_pending(label: str, pk: int, name: str) -> None:
    """Borra la original del storage privado, sin dejar caer la operación.

    Si el borrado falla, la fila ya quedó consistente y lo publicado ya está
    difuminado: queda un archivo huérfano, que es un problema de limpieza y no
    de privacidad de lo que se publicó.
    """
    if not name:
        return
    from .storage import pending_photo_storage  # noqa: PLC0415

    try:
        pending_photo_storage().delete(name)
    except OSError:
        logger.exception(
            "Quedó sin borrar la foto pendiente de %s #%s.",
            label,
            pk,
        )
