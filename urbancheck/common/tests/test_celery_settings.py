"""Límites de tiempo de Celery (C-07).

Reemplazan los ``TODO`` de la plantilla de cookiecutter por valores que salen
de lo que tardan las tareas: el difuminado, alrededor de 1,1 s por foto, y un
intento de comparación de cierres, hasta ``RESOLUTION_COMPARISON_TIMEOUT_SECONDS``
(30 s). Cada reintento de la comparación es una ejecución nueva de la tarea.
"""

from pathlib import Path

from django.conf import settings

ROOT = Path(__file__).resolve().parents[3]


def test_the_soft_limit_fits_one_comparison_attempt_with_margin():
    """El corte blando llega después del timeout del pedido, con margen para
    bajar las imágenes y registrar el fallo."""
    timeout = settings.RESOLUTION_COMPARISON_TIMEOUT_SECONDS

    assert 2 * timeout <= settings.CELERY_TASK_SOFT_TIME_LIMIT


def test_the_hard_limit_leaves_room_to_handle_the_soft_one():
    soft = settings.CELERY_TASK_SOFT_TIME_LIMIT
    hard = settings.CELERY_TASK_TIME_LIMIT

    assert soft < hard <= soft + 30


def test_no_placeholder_is_left():
    text = (ROOT / "config" / "settings" / "base.py").read_text(encoding="utf-8")

    assert "TODO: set to whatever value is adequate" not in text
