"""Sanea las fotos de perfil ya guardadas (Sprint 5, punto 5.2, SEC-10).

La foto de perfil no se difumina, pero desde el Sprint 5 se guarda sin
metadatos. Las subidas antes pueden traer el GPS, el modelo del teléfono y la
fecha: este comando las reescribe sin ellos, con la orientación aplicada.

Las fotos de reportes, cierres y apelaciones **no** van por acá: las anteriores
a US-041 las difumina ``anonymize_existing_photos``, que de paso también les saca
los metadatos.

**Toca archivos publicados.** Sin ``--apply`` solo cuenta lo que haría.
"""

from __future__ import annotations

from functools import partial
from pathlib import PurePath

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from urbancheck.anonymization.service import AnonymizationError
from urbancheck.users.models import User


class Command(BaseCommand):
    help = (
        "Reescribe sin metadatos las fotos de perfil ya guardadas. "
        "Sin --apply no cambia nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Reescribe de verdad. Sin esto, solo cuenta.",
        )

    def handle(self, *args, apply=False, **options):
        users = User.objects.exclude(avatar="").order_by("pk")
        if not apply:
            self.stdout.write(
                f"Simulacro: {users.count()} fotos de perfil por sanear. "
                "Nada cambió; correr con --apply para reescribirlas.",
            )
            return

        cleaned = unreadable = missing = 0
        for pk in users.values_list("pk", flat=True):
            outcome = self._clean(pk)
            cleaned += outcome == "cleaned"
            unreadable += outcome == "unreadable"
            missing += outcome == "missing"
        self.stdout.write(
            f"{cleaned} saneadas, {unreadable} ilegibles (sin tocar), "
            f"{missing} sin archivo.",
        )

    def _clean(self, pk: int) -> str:
        """Vuelve a asignar el archivo: el campo lo reescribe sin metadatos.

        El saneamiento vive en ``MetadataFreeImageField`` y no se repite acá;
        así una foto se reencodea una sola vez.
        """
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=pk)
                storage, old_name = user.avatar.storage, user.avatar.name
                if not storage.exists(old_name):
                    return "missing"
                with user.avatar.open("rb") as file:
                    user.avatar = ContentFile(file.read(), name=PurePath(old_name).name)
                user.save(update_fields=["avatar"])
                transaction.on_commit(partial(storage.delete, old_name))
        except AnonymizationError:
            self.stderr.write(f"Foto de perfil ilegible: usuario #{pk}.")
            return "unreadable"
        return "cleaned"
