"""Tareas periódicas de la app de reportes."""

from config.celery_app import app

from .archival import run_archival
from .resolution import run_confirmation


@app.task()
def archive_stale_reports() -> dict[str, int]:
    """Verificación diaria del archivado por inactividad (US-031).

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
