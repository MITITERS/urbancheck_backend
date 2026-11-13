from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "urbancheck.notifications"

    def ready(self):
        # Importado por su efecto: engancha el receiver del cambio de estado.
        from . import signals  # noqa: F401, PLC0415
