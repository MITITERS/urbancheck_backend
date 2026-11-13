"""Lista y borra los archivos de ``MEDIA_ROOT`` que ninguna fila referencia (N-08).

Desde N-08 los archivos se borran con su fila, pero quedan los de antes y los
que no se pudieron borrar (el error se registra y la fila se borra igual).
Este comando los encuentra recorriendo ``MEDIA_ROOT`` y comparando contra
todos los ``FileField`` de los modelos, más las imágenes denunciadas por dato
personal que todavía esperan resolución.

**Borra archivos.** Sin ``--apply`` solo los lista.
"""

from __future__ import annotations

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

from urbancheck.common.media_cleanup import file_fields


def referenced_names() -> set[str]:
    names: set[str] = set()
    for model in apps.get_models():
        for field in file_fields(model):
            names.update(
                model._default_manager.exclude(**{field.attname: ""})  # noqa: SLF001
                .values_list(field.attname, flat=True)
                .iterator(),
            )
    # Una solicitud por dato personal guarda el nombre de la imagen denunciada
    # como texto: mientras exista, el archivo no es huérfano.
    complaint = apps.get_model("reports", "ReportComplaint")
    names.update(
        complaint.objects.exclude(image_name="")
        .values_list("image_name", flat=True)
        .iterator(),
    )
    return names


def media_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            yield path.relative_to(root).as_posix()


class Command(BaseCommand):
    help = (
        "Lista los archivos de MEDIA_ROOT sin registro en la base. "
        "Con --apply, los borra."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Borra de verdad. Sin esto, solo lista.",
        )

    def handle(self, *args, apply=False, **options):
        root = Path(settings.MEDIA_ROOT)
        referenced = referenced_names()
        orphans = [name for name in media_files(root) if name not in referenced]
        for name in orphans:
            self.stdout.write(name)
            if apply:
                (root / name).unlink(missing_ok=True)
        verb = "Borrados" if apply else "Huérfanos (sin --apply no se borra nada)"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {len(orphans)}"))
