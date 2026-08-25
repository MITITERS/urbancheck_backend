from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "urbancheck.users"
    verbose_name = _("Users")

    def ready(self):
        # Importado por su efecto: registra los receivers de allauth.
        from . import signals  # noqa: F401, PLC0415
