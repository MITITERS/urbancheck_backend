from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "urbancheck.reports"

    def ready(self):
        """Registra qué pasa después de difuminar cada foto (US-042).

        Los efectos dependen del modelo —un cierre dispara la comparación de
        US-015, un reporte fallido avisa a su autor— pero el circuito de
        difuminado es uno solo. Se registran como hooks acá, y no dentro de
        ``anonymization``, para que esa app no tenga que importar ``reports``:
        la dependencia va en un solo sentido.
        """
        # Imports locales: `ready` corre después de cargar los modelos, y a
        # nivel de módulo esto sería una importación circular.
        from urbancheck.anonymization.pipeline import register_hooks  # noqa: PLC0415

        from . import photo_hooks  # noqa: PLC0415

        register_hooks(
            "reports.report",
            on_failure=photo_hooks.report_photo_failed,
        )
        register_hooks(
            "reports.resolutionevidence",
            on_success=photo_hooks.evidence_photo_ready,
            on_failure=photo_hooks.evidence_photo_failed,
        )
        register_hooks(
            "reports.resolutionappeal",
            on_failure=photo_hooks.appeal_photo_failed,
        )
