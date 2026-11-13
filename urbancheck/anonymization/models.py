"""Estado de procesamiento de una foto (US-042).

La publicación queda subordinada al procesamiento: un reporte existe desde que
el ciudadano lo envía, pero no es público hasta que su imagen fue anonimizada.
El estado es **de la imagen**, no del reporte: la máquina de estados de US-013
no se toca, se agrega una condición de visibilidad que se evalúa antes de
servir cualquier vista pública.

El mixin es abstracto y lo heredan los tres modelos que reciben una foto
—reporte, evidencia de cierre y apelación—, para que el circuito sea uno solo.
Un cuarto modelo con foto que no lo herede es un agujero en RN-11, y por eso
hay un test que recorre los serializers para que no aparezca.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from .storage import pending_photo_storage
from .storage import pending_upload_to

if TYPE_CHECKING:
    from django.db.models.fields.files import ImageFieldFile


class PhotoStatus(models.TextChoices):
    PENDIENTE = "pendiente", "En procesamiento"
    PROCESADA = "procesada", "Procesada"
    FALLIDA = "fallida", "No se pudo procesar"


class PendingPhotoMixin(models.Model):
    """Los cuatro campos que sostienen la publicación diferida.

    ``photo`` (que declara cada modelo concreto) es siempre la versión
    difuminada: o está vacía, o pasó por el servicio. Esa es la invariante que
    hace cierto el escenario 6, y se sostiene en dos lugares —``save`` acá y un
    ``CheckConstraint`` en cada modelo—, porque el constraint alcanza también a
    ``update()`` y ``bulk_update()``, que no pasan por ``save``.
    """

    if TYPE_CHECKING:
        #: Lo declara cada modelo concreto, con su propio ``upload_to``. Acá
        #: solo se anota para que ``save`` pueda consultarlo.
        photo: ImageFieldFile

    #: La original, en el storage privado. Se borra apenas termina el
    #: procesamiento, salga bien o mal.
    photo_pending = models.FileField(
        "foto sin procesar",
        upload_to=pending_upload_to,
        storage=pending_photo_storage,
        blank=True,
    )
    photo_status = models.CharField(
        "estado del procesamiento",
        max_length=10,
        choices=PhotoStatus.choices,
        default=PhotoStatus.PENDIENTE,
    )
    #: Para diagnóstico: cuántas veces se intentó antes de darlo por perdido.
    photo_attempts = models.PositiveSmallIntegerField(
        "intentos de procesamiento",
        default=0,
    )
    photo_failed_at = models.DateTimeField(
        "fallo definitivo",
        null=True,
        blank=True,
    )
    #: Cuándo entró a la cola. Es lo que mide el reencolado de lo vencido, y
    #: tiene que ser propio y no la fecha de alta de la fila: una foto que se
    #: reemplaza hoy sobre un reporte del año pasado parecería vencida al
    #: instante y se reencolaría sola en la primera verificación.
    photo_queued_at = models.DateTimeField(
        "encolada",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Rechaza guardar una foto que no pasó por el difuminado.

        Es la misma condición que el constraint, un paso antes y con un mensaje
        que se entiende: acá caen el shell, los fixtures y cualquier código que
        arme la instancia a mano.
        """
        if self.photo and self.photo_status != PhotoStatus.PROCESADA:
            msg = (
                f"{type(self).__name__}: no se puede guardar una foto con el "
                f"procesamiento en «{self.photo_status}». Solo se publica una "
                f"imagen ya difuminada (US-042, RN-11)."
            )
            raise ValueError(msg)
        return super().save(*args, **kwargs)

    @property
    def photo_is_processing(self) -> bool:
        return self.photo_status == PhotoStatus.PENDIENTE

    @property
    def photo_is_ready(self) -> bool:
        return self.photo_status == PhotoStatus.PROCESADA

    @property
    def photo_has_failed(self) -> bool:
        return self.photo_status == PhotoStatus.FALLIDA
