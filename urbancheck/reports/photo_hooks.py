"""Qué pasa después de difuminar cada foto (US-042).

El circuito de difuminado es genérico y vive en ``anonymization.pipeline``.
Esto es lo específico de cada modelo, registrado desde ``ReportsConfig.ready``.

Un reporte que termina bien no necesita nada más: el solo hecho de quedar en
``procesada`` lo vuelve visible, porque la visibilidad se resuelve en el
queryset. Los que sí necesitan algo son el cierre —que dispara la comparación
de US-015— y cualquiera que falle, que tiene que avisarle a quien subió la foto.
"""

from __future__ import annotations

from urbancheck.notifications.services import notify_photo_processing_failed

from .comparison import enqueue_comparison
from .comparison import mark_unavailable


def report_photo_failed(report, code: str) -> None:
    """El reporte no se publica y su autor se entera (escenario 5).

    El reporte **no se borra**: sigue existiendo, sigue siendo editable —está en
    *pendiente de validación*, y ``is_editable`` lo permite— y su autor puede
    reemplazar la foto, que vuelve a entrar a la cola. Borrarlo por él le
    sacaría de las manos la decisión.
    """
    notify_photo_processing_failed(report, report=report)


def evidence_photo_ready(evidence) -> None:
    """Ahora sí hay una foto difuminada que comparar (US-015)."""
    enqueue_comparison(evidence)


def evidence_photo_failed(evidence, code: str) -> None:
    """El cierre queda sin foto, pero el cierre ya ocurrió.

    La máquina de estados **no** se toca: el reporte ya pasó a *resuelto
    pendiente de confirmación* y el ciudadano ya recibió el aviso. Revertir eso
    ahora abriría un caso que la historia no plantea y que el operario no pidió.
    Lo que queda es un parte de trabajo con descripción y sin imagen, marcado
    como fallido, y una comparación que no se puede hacer.
    """
    mark_unavailable(evidence.pk, "photo_unavailable")
    notify_photo_processing_failed(evidence, report=evidence.report)


def appeal_photo_failed(appeal, code: str) -> None:
    """La objeción queda registrada sin su evidencia fotográfica.

    Igual que con el cierre: la transición ya ocurrió y el reporte ya volvió a
    *En proceso*. Lo que falta es la foto, y su autor recibe el aviso.
    """
    notify_photo_processing_failed(appeal, report=appeal.report)
