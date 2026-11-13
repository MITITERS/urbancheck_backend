from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "urbancheck.users"
    verbose_name = _("Users")

    def ready(self):
        # Importados por su efecto: registran los receivers de allauth y los
        # del registro de seguridad (login, contraseñas, altas de cuentas de
        # trabajo), que se enganchan acá porque ``common`` no es una app.
        from urbancheck.common import media_cleanup  # noqa: PLC0415
        from urbancheck.common import security_receivers  # noqa: F401, PLC0415

        from . import signals  # noqa: F401, PLC0415
        from .models import User  # noqa: PLC0415

        # El avatar se borra con la cuenta y al reemplazarse (N-08).
        media_cleanup.connect(User)
