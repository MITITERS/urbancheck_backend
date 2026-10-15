"""
With these settings, tests run faster.
"""

from .base import *  # noqa: F403
from .base import LOGGING
from .base import TEMPLATES
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
ALLOWED_HOSTS = ["*"]
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="GdWOU2gP7ftarifjYMMtonjGKqxp1EMZjpQIxiHYXvOYWY0W1kcPZnC3amkaepce",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# DEBUGGING FOR TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore[index]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "http://media.testserver/"
# Your stuff...
# ------------------------------------------------------------------------------
# La comparación de cierres (US-015) queda "configurada" para que los tests
# ejerciten el circuito completo. Ninguno sale a la red: ``conftest.py`` bloquea
# el cliente, y los que necesitan una respuesta la simulan.
VISION_PROVIDER = "openai_compatible"
RESOLUTION_COMPARISON_API_KEY = "test-key"

# CACHES
# ------------------------------------------------------------------------------
# En memoria y no sobre Redis: los contadores de los límites de tasa no pueden
# pasar de un test a otro ni de una corrida a otra. ``conftest.py`` lo vacía
# antes de cada test.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "urbancheck-tests",
    },
}

# LOGGING
# ------------------------------------------------------------------------------
# El registro de seguridad no escribe archivo en los tests y propaga a la raíz,
# que es donde ``caplog`` lo escucha.
LOGGING["handlers"].pop("security_file", None)
LOGGING["loggers"]["security"] = {"handlers": [], "level": "INFO", "propagate": True}
