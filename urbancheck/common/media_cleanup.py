"""Los archivos se van con la fila (N-08).

Borrar un reporte, un cierre, una apelación o una cuenta dejaba la foto, la
original pendiente y el avatar en disco: la supresión del art. 16 de la Ley
25.326 no era efectiva. Lo mismo con la foto o el avatar que se reemplazan.

El borrado del archivo espera a que la transacción se confirme
(``transaction.on_commit``): si se revierte, la fila sigue y su archivo
también. Un archivo que no se pudo borrar se registra y lo levanta después
``purge_orphan_media``.
"""

from __future__ import annotations

import logging
from functools import partial

from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.db.models.fields.files import FileField
from django.db.models.signals import post_delete
from django.db.models.signals import pre_save

logger = logging.getLogger(__name__)


def file_fields(model) -> list[FileField]:
    return [field for field in model._meta.get_fields() if isinstance(field, FileField)]  # noqa: SLF001


def delete_on_commit(storage, name: str) -> None:
    if name:
        transaction.on_commit(partial(_delete, storage, name))


def _delete(storage, name: str) -> None:
    try:
        storage.delete(name)
    except OSError:
        logger.exception("Quedó sin borrar el archivo %s.", name)


def _delete_files(sender, instance, **kwargs) -> None:
    for field in file_fields(sender):
        field_file: FieldFile = getattr(instance, field.attname)
        if field_file:
            delete_on_commit(field_file.storage, field_file.name)


def _delete_replaced_files(sender, instance, update_fields=None, **kwargs) -> None:
    if instance._state.adding or instance.pk is None:  # noqa: SLF001
        return
    fields = [
        field
        for field in file_fields(sender)
        if update_fields is None or field.attname in update_fields
    ]
    if not fields:
        return
    previous = (
        sender._default_manager.filter(pk=instance.pk)  # noqa: SLF001
        .values(*(field.attname for field in fields))
        .first()
    )
    if previous is None:
        return
    for field in fields:
        old_name = previous[field.attname]
        if old_name and old_name != getattr(instance, field.attname).name:
            delete_on_commit(field.storage, old_name)


def connect(*models) -> None:
    for model in models:
        post_delete.connect(_delete_files, sender=model, weak=False)
        pre_save.connect(_delete_replaced_files, sender=model, weak=False)
