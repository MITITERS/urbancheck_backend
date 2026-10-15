from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "urbancheck.users"
    verbose_name = _("Users")

    def ready(self):
        # Importados por su efecto: registran los receivers de allauth y los
        # del registro de seguridad (login, contraseñas, altas de cuentas de
        # trabajo), que se enganchan acá porque ``common`` no es una app.
        from urbancheck.common import security_receivers  # noqa: F401, PLC0415

        from . import signals  # noqa: F401, PLC0415
