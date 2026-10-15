"""Difumina las fotos publicadas antes de US-041 (US-042, escenario 9).

La migración ``reports/0012`` dejó las fotos que ya existían marcadas como
procesadas sin procesarlas. Este comando las recorre —reportes, evidencias de
cierre y apelaciones—, les aplica el mismo servicio que a toda foto nueva y
reemplaza la publicada por la difuminada. Si alguna no se puede procesar, se
retira y se avisa al autor, igual que con un fallo definitivo.

**Toca archivos publicados.** Sin ``--apply`` solo cuenta lo que haría; con
``--apply`` los cambios no se deshacen. Es una operación que el equipo tiene que
autorizar antes de correrla sobre datos reales.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps
from django.core.management.base import BaseCommand

from urbancheck.anonymization.models import PendingPhotoMixin
from urbancheck.anonymization.pipeline import label_of
from urbancheck.anonymization.pipeline import legacy_photos
from urbancheck.anonymization.pipeline import reprocess_legacy_photo


class Command(BaseCommand):
    help = (
        "Difumina las fotos publicadas que nunca pasaron por la anonimización. "
        "Sin --apply no cambia nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Procesa de verdad. Sin esto, solo cuenta.",
        )

    def handle(self, *args, apply=False, **options):
        models = [
            model for model in apps.get_models() if issubclass(model, PendingPhotoMixin)
        ]
        total = Counter()
        for model in models:
            pks = list(legacy_photos(model).values_list("pk", flat=True))
            name = model._meta.verbose_name_plural  # noqa: SLF001
            if not apply:
                self.stdout.write(f"{name}: {len(pks)} por procesar")
                total["pending"] += len(pks)
                continue
            results = Counter(reprocess_legacy_photo(label_of(model), pk) for pk in pks)
            total.update(results)
            self.stdout.write(
                f"{name}: {results['processed']} difuminadas, "
                f"{results['failed']} retiradas, "
                f"{results['missing']} sin archivo",
            )
        if not apply:
            self.stdout.write(
                f"Simulacro: {total['pending']} fotos por procesar. "
                "Nada cambió; correr con --apply para procesarlas.",
            )
