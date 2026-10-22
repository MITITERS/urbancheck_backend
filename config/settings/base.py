# ruff: noqa: ERA001, E501
"""Base settings to build other settings files upon."""

import ssl
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
# urbancheck/
APPS_DIR = BASE_DIR / "urbancheck"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "America/Argentina/Cordoba"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
# from django.utils.translation import gettext_lazy as _
# LANGUAGES = [
#     ('en', _('English')),
#     ('fr-fr', _('French')),
#     ('pt-br', _('Portuguese')),
# ]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.humanize", # Handy template tags
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.mfa",
    "allauth.socialaccount",
    "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

LOCAL_APPS = [
    # Antes de ``users``: el admin de usuarios arma un ModelForm en tiempo de
    # importación sobre la FK a Municipality, que ya tiene que estar cargada.
    "urbancheck.municipalities",
    "urbancheck.users",
    "urbancheck.reports",
    "urbancheck.notifications",
    "urbancheck.anonymization",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "urbancheck.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Registro de seguridad (401, 403, 429 y el contexto de ``log_event``).
    # El de allauth va después: tiene que corregir el ``400`` del bloqueo de
    # login a ``429`` antes de que el registro mire la respuesta.
    "urbancheck.common.security.SecurityContextMiddleware",
    "urbancheck.common.security.HeadlessLockoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# Dónde espera la foto original hasta que la tarea la difumina (US-042). Fuera
# de MEDIA_ROOT a propósito: `/media/` se sirve entero, y ahí adentro estaría
# publicada la foto sin difuminar. Ver `urbancheck/anonymization/storage.py`.
PENDING_PHOTO_ROOT = env(
    "DJANGO_PENDING_PHOTO_ROOT",
    default=str(BASE_DIR / "pending_media"),
)
# https://docs.djangoproject.com/en/dev/ref/settings/#storages
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    # La ubicación no viaja en OPTIONS: el storage la lee de
    # `PENDING_PHOTO_ROOT` en cada uso, y así se puede redirigir sin recrear
    # nada. Sin `base_url`: `photo_pending.url` levanta ValueError, y exponer
    # la original por descuido falla en vez de filtrarla.
    "pending_photos": {
        "BACKEND": "urbancheck.anonymization.storage.PendingPhotoStorage",
    },
}

# La foto sube sin pasar por un temporal a disco (US-041), que es lo que Django
# hace por defecto con todo archivo de más de 2,5 MB: de ahí no la borra nadie.
# https://docs.djangoproject.com/en/dev/ref/settings/#file-upload-handlers
FILE_UPLOAD_HANDLERS = ["urbancheck.anonymization.uploads.MemoryOnlyUploadHandler"]
PHOTO_MAX_UPLOAD_BYTES = env.int("DJANGO_PHOTO_MAX_UPLOAD_MB", default=15) * 1024 * 1024
# El cuerpo entero del request: la foto más los campos de texto que la acompañan.
FILE_UPLOAD_MAX_MEMORY_SIZE = PHOTO_MAX_UPLOAD_BYTES + 1024 * 1024

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "urbancheck.users.context_processors.allauth_settings",
            ],
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = ['"Mititers" <mititerspf2026@gmail.com>']
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# https://cookiecutter-django.readthedocs.io/en/latest/settings.html#other-environment-settings
# Force the `admin` sign in process to go through the `django-allauth` workflow
DJANGO_ADMIN_FORCE_ALLAUTH = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
# Registro de eventos de seguridad (logger ``security``, ver
# ``urbancheck/common/security.py``): logins, bloqueos, cambios de contraseña,
# altas de cuentas de trabajo, denuncias y respuestas 401/403/429. Va a un
# archivo propio con rotación por tamaño, además de la consola. Vacío
# desactiva el archivo y deja solo la consola.
SECURITY_LOG_FILE = env(
    "DJANGO_SECURITY_LOG_FILE",
    default=str(BASE_DIR / "logs" / "security.log"),
)
SECURITY_LOG_MAX_BYTES = env.int("DJANGO_SECURITY_LOG_MAX_MB", default=10) * 1024 * 1024
SECURITY_LOG_BACKUP_COUNT = env.int("DJANGO_SECURITY_LOG_BACKUP_COUNT", default=10)


def security_logging(log_file: str) -> tuple[dict, dict]:
    """Handlers y logger de ``security``, para sumar a cualquier ``LOGGING``.

    Es una función porque ``production.py`` arma su propio ``LOGGING`` y el
    registro de seguridad no puede faltar en ninguno de los dos.
    """
    handlers: dict = {}
    names = ["console"]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers["security_file"] = {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": log_file,
            "maxBytes": SECURITY_LOG_MAX_BYTES,
            "backupCount": SECURITY_LOG_BACKUP_COUNT,
            "encoding": "utf-8",
            "formatter": "security",
        }
        names.append("security_file")
    logger = {"handlers": names, "level": "INFO", "propagate": False}
    return handlers, logger


_security_handlers, _security_logger = security_logging(SECURITY_LOG_FILE)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
        "security": {"format": "%(asctime)s %(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        **_security_handlers,
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {"security": _security_logger},
}

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")
REDIS_SSL = REDIS_URL.startswith("rediss://")

# CACHES
# ------------------------------------------------------------------------------
# Compartido sobre Redis en todos los entornos: los contadores de los límites
# de allauth y de DRF viven acá, y con un cache por proceso cada worker de
# gunicorn llevaría su propia cuenta y el límite real se multiplicaría por la
# cantidad de workers.
# https://docs.djangoproject.com/en/dev/topics/cache/#redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("DJANGO_CACHE_URL", default=REDIS_URL),
    },
}

# PROXIES DE CONFIANZA
# ------------------------------------------------------------------------------
# Cuántos proxies propios (Nginx, Traefik) hay delante de Django. Con cero se
# ignora ``X-Forwarded-For`` y la IP es la de la conexión; detrás de un proxy
# hay que poner 1, o todos los límites por IP contarían la IP del proxy y un
# solo cliente agotaría el cupo de todos. Lo leen DRF (``NUM_PROXIES``),
# allauth (``ALLAUTH_TRUSTED_PROXY_COUNT``) y el registro de seguridad.
NUM_PROXIES = env.int("DJANGO_NUM_PROXIES", default=0)
ALLAUTH_TRUSTED_PROXY_COUNT = NUM_PROXIES

# Celery
# ------------------------------------------------------------------------------
if USE_TZ:
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE} if REDIS_SSL else None
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_REDIS_BACKEND_USE_SSL = CELERY_BROKER_USE_SSL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-extended
CELERY_RESULT_EXTENDED = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-always-retry
# https://github.com/celery/celery/pull/6122
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-max-retries
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_TIME_LIMIT = 5 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_SOFT_TIME_LIMIT = 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
# El scheduler es el de base de datos, así que esta tabla es el **default** con
# el que arranca: django-celery-beat la sincroniza al levantar y después la
# entrada se administra desde el admin. Se declara acá para que un despliegue
# nuevo tenga la verificación diaria de US-041 andando sin un paso manual.
CELERY_BEAT_SCHEDULE = {
    "archive-stale-reports": {
        "task": "urbancheck.reports.tasks.archive_stale_reports",
        # Cada quince minutos, por lo mismo que la confirmación de abajo: el
        # plazo es configurable desde que existe
        # ``DJANGO_ARCHIVAL_INACTIVITY_DAYS``, y una corrida diaria dejaba el
        # archivado automático **sin poder demostrarse** —había que fechar un
        # reporte en el pasado y después esperar a la madrugada—.
        #
        # Corría a las 3:30 para no mover reportes en horario de uso del
        # municipio. Esa razón no se sostiene para esta tarea: solo alcanza
        # reportes *pendientes de validación* que nadie tocó en meses, que por
        # definición no están en la cola de trabajo de nadie. Y el aviso al
        # autor se lee mejor a las diez de la mañana que a las tres.
        "schedule": crontab(minute="*/15"),
    },
    "confirm-resolved-reports": {
        "task": "urbancheck.reports.tasks.confirm_resolved_reports",
        # Cada quince minutos y no una vez al día: el plazo de objeción es
        # configurable y la review lo baja a minutos, así que una corrida diaria
        # dejaría la confirmación automática sin poder demostrarse.
        "schedule": crontab(minute="*/15"),
    },
    "requeue-stale-pending-photos": {
        "task": "urbancheck.anonymization.tasks.requeue_stale_pending_photos",
        # El seguro contra el mensaje que el broker perdió (US-042). En la
        # práctica no encuentra nada; el día que encuentre algo, es un reporte
        # que no se habría publicado nunca.
        "schedule": crontab(minute="*/15"),
    },
}
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-task_send_sent_event
CELERY_TASK_SEND_SENT_EVENT = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-hijack-root-logger
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
# UrbanCheck
# ------------------------------------------------------------------------------
# Municipalidad a la que se asocian los reportes nuevos (US-034). Vacío significa
# "la única registrada"; se vuelve obligatorio cuando haya más de una.
ACTIVE_MUNICIPALITY_ID = env.int("DJANGO_ACTIVE_MUNICIPALITY_ID", default=None)

# Radio dentro del cual un validador puede confirmar un reporte en terreno
# (US-036). Es un único parámetro y no una constante repartida por el código;
# la verificación se hace siempre en el servidor, nunca en el dispositivo.
VALIDATION_RADIUS_METERS = env.int("DJANGO_VALIDATION_RADIUS_METERS", default=50)

# Radio dentro del cual un reporte activo de la misma categoría se considera el
# mismo problema (US-026) y el nuevo no se crea (US-032). Absorbe el error del
# GPS de un teléfono en la calle (10 a 20 m) sin unificar dos baches distintos
# de la misma cuadra. Como el radio de US-036 y el umbral de US-040, es un
# único parámetro y se lee en cada evaluación. El criterio completo vive en
# ``urbancheck.reports.duplicates``.
DUPLICATE_REPORT_RADIUS_METERS = env.int(
    "DJANGO_DUPLICATE_REPORT_RADIUS_METERS",
    default=30,
)

# Cuántas confirmaciones distintas de vecinos validan un reporte sin que un
# validador vaya al lugar (US-040). No cuentan ni el autor ni las cuentas de
# trabajo: el conteo lo resuelve ``Report.confirmation_count()``.
#
# Va acá y no como constante en el código porque el escenario 7 pide poder
# moverlo sin redeploy; el módulo lo lee en cada evaluación.
COLLECTIVE_VALIDATION_THRESHOLD = env.int(
    "DJANGO_COLLECTIVE_VALIDATION_THRESHOLD",
    default=10,
)

# Días sin interacción tras los cuales un reporte pendiente de validación se
# archiva solo (US-031).
#
# Cuenta desde la **última señal de vida** —creación, comentario o me gusta—, no
# desde el alta: un reporte que alguien apoyó hace una semana no está
# abandonado, por viejo que sea.
#
# Acá sí va en días y no en minutos, a diferencia de los otros plazos: el
# archivado se demuestra fechando un reporte en el pasado, no esperando a que
# venza.
ARCHIVAL_INACTIVITY_DAYS = env.int("DJANGO_ARCHIVAL_INACTIVITY_DAYS", default=90)

# Cuánto tiempo sigue dibujado en el mapa un reporte ya resuelto.
#
# El mapa muestra lo que pasa hoy; los resueltos acumulados de todos los meses
# lo convierten en un registro histórico. Pasado el plazo el reporte **solo**
# deja de dibujarse: sigue en el feed, en el detalle y en el panel, no se
# archiva ni cambia de estado.
#
# **En minutos y no en días**, por lo mismo que la ventana de objeción: el
# default son quince días y una demostración necesita poder bajarlo a un par de
# minutos sin tocar código.
MAP_RESOLVED_RETENTION_MINUTES = env.int(
    "DJANGO_MAP_RESOLVED_RETENTION_MINUTES",
    default=15 * 24 * 60,
)

# Ventana durante la cual el autor puede objetar el cierre de un operario antes
# de que el reporte quede confirmado como Resuelto (US-047).
#
# **En minutos y no en días** a propósito: el default son siete días, pero la
# demostración en la review necesita poder bajarlo a un par de minutos sin tocar
# código, y un parámetro expresado en días no lo permite.
RESOLUTION_OBJECTION_MINUTES = env.int(
    "DJANGO_RESOLUTION_OBJECTION_MINUTES",
    default=7 * 24 * 60,
)

# Estadísticas del panel (US-050): desde qué porcentaje de cierres apelados el
# panel destaca el indicador. Es configurable porque qué es "mucho" lo decide
# cada despliegue, no el código.
STATS_APPEAL_ALERT_PERCENT = env.int("DJANGO_STATS_APPEAL_ALERT_PERCENT", default=20)

# El enlace para compartir un reporte (US-030). Apunta a la ruta pública del
# panel, ``/r/<token>``, que es también la que abre la app si está instalada.
# En desarrollo conviene ``http://localhost:5173/r/{token}``.
PUBLIC_REPORT_URL = env(
    "DJANGO_PUBLIC_REPORT_URL",
    default="https://urbancheck.com.ar/r/{token}",
)
# A dónde sigue una persona que abre ese enlace: la página pública del panel.
# ``/r/<token>`` lo responde el backend con las etiquetas de vista previa para
# las redes (Open Graph) y redirige acá. En producción es la misma raíz, así que
# alcanza con una ruta relativa; en desarrollo, el panel vive en otro puerto:
# ``http://localhost:5173/reporte/{token}``.
PUBLIC_REPORT_PAGE_URL = env(
    "DJANGO_PUBLIC_REPORT_PAGE_URL",
    default="/reporte/{token}",
)

# Con cuánta antelación se le avisa al autor que el plazo está por vencer.
RESOLUTION_OBJECTION_WARNING_MINUTES = env.int(
    "DJANGO_RESOLUTION_OBJECTION_WARNING_MINUTES",
    default=24 * 60,
)

# Plazo para resolver una solicitud de revisión por dato personal visible
# (US-043, RN-12). Corre desde la **recepción** de la solicitud; pasado el plazo
# la bandeja del administrador la señala como fuera de plazo.
#
# **En minutos y no en horas**, por lo mismo que la ventana de objeción: el
# default son 24 horas y una demostración necesita ver vencer una solicitud.
PERSONAL_DATA_REVIEW_MINUTES = env.int(
    "DJANGO_PERSONAL_DATA_REVIEW_MINUTES",
    default=24 * 60,
)

# Comparación automática del antes y el después de un cierre (US-015).
#
# El cliente habla el dialecto de chat completions de OpenAI, que ofrecen Gemini,
# Groq, OpenRouter y Ollama: cambiar de proveedor es cambiar estas variables. El
# default es el free tier de Gemini en Google AI Studio.
#
# **Sin clave, la función queda apagada**: cada cierre se registra como
# "comparación no disponible" y el circuito sigue igual. Es informativa y nunca
# puede bloquear un cierre.
# Qué servicio de visión se usa (ver ``urbancheck/reports/vision.py``). Vacío
# es el proveedor nulo: no se compara nada y ninguna foto sale del servidor.
# ``openai_compatible`` es el adaptador de chat completions (Gemini, Groq,
# OpenRouter, Ollama), que usa las variables de abajo.
VISION_PROVIDER = env("DJANGO_VISION_PROVIDER", default="")
RESOLUTION_COMPARISON_API_KEY = env("DJANGO_RESOLUTION_COMPARISON_API_KEY", default="")
RESOLUTION_COMPARISON_BASE_URL = env(
    "DJANGO_RESOLUTION_COMPARISON_BASE_URL",
    default="https://generativelanguage.googleapis.com/v1beta/openai/",
)
RESOLUTION_COMPARISON_MODEL = env(
    "DJANGO_RESOLUTION_COMPARISON_MODEL",
    default="gemini-3.6-flash",
)
# Reintentos ante fallos transitorios (timeout, 429, 5xx) antes de darla por no
# ANONIMIZACIÓN DIFERIDA (US-042)
# ------------------------------------------------------------------------------
# Cuántas veces se reintenta una foto cuyo detector falló, y con qué espera
# inicial entre intentos (se duplica en cada uno). Un fallo permanente —un
# archivo que no se puede abrir— no se reintenta ninguna vez.
ANONYMIZATION_MAX_RETRIES = env.int("DJANGO_ANONYMIZATION_MAX_RETRIES", default=3)
ANONYMIZATION_RETRY_BASE_SECONDS = env.int(
    "DJANGO_ANONYMIZATION_RETRY_BASE_SECONDS",
    default=30,
)
# A partir de cuánto una foto en cola se considera perdida y se reencola. Cubre
# el mensaje que el broker nunca entregó: sin esto el reporte queda invisible
# para siempre y ni siquiera falló, así que su autor no recibe ningún aviso.
ANONYMIZATION_STALE_MINUTES = env.int("DJANGO_ANONYMIZATION_STALE_MINUTES", default=30)
# Carpeta **no versionada** con el set de referencia de US-041: fotos reales con
# rostros y patentes y su ``manifest.json`` de etiquetas. La leen el comando
# ``benchmark_anonymization`` y los tests de detección, que se saltean si falta.
# Nunca va dentro del control de versiones ni de la imagen de Docker.
ANONYMIZATION_REFERENCE_SET = env(
    "DJANGO_ANONYMIZATION_REFERENCE_SET",
    default=str(BASE_DIR / "benchmark_data" / "anonymization"),
)

# disponible. Una respuesta fuera de formato no se reintenta.
RESOLUTION_COMPARISON_MAX_RETRIES = env.int(
    "DJANGO_RESOLUTION_COMPARISON_MAX_RETRIES",
    default=3,
)
# Por debajo del ``CELERY_TASK_SOFT_TIME_LIMIT``: la tarea tiene que poder
# registrar el fallo antes de que Celery la corte.
RESOLUTION_COMPARISON_TIMEOUT_SECONDS = env.int(
    "DJANGO_RESOLUTION_COMPARISON_TIMEOUT_SECONDS",
    default=30,
)
# Lado mayor con el que viajan las imágenes. Alcanza para ver un bache y ahorra
# cuota del plan gratuito.
RESOLUTION_COMPARISON_MAX_SIDE_PX = env.int(
    "DJANGO_RESOLUTION_COMPARISON_MAX_SIDE_PX",
    default=1024,
)

# django-allauth
# ------------------------------------------------------------------------------
ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_LOGIN_METHODS = {"email"}
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_EMAIL_VERIFICATION = "optional"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER = "urbancheck.users.adapters.AccountAdapter"
# https://docs.allauth.org/en/latest/account/forms.html
ACCOUNT_FORMS = {"signup": "urbancheck.users.forms.UserSignupForm"}
ACCOUNT_SIGNUP_FORM_CLASS = "urbancheck.users.signup_forms.HeadlessUserSignupForm"
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER = "urbancheck.users.adapters.SocialAccountAdapter"
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_FORMS = {"signup": "urbancheck.users.forms.UserSocialSignupForm"}
# Límites de intentos (deuda de seguridad del Sprint 4). Formato de allauth:
# ``cantidad/período/clave``, varios separados por coma; ``key`` es la cuenta
# (el correo) e ``ip`` la IP del cliente. La ventana es deslizante: allauth
# guarda la marca de cada intento en el cache y cuenta los del período.
# https://docs.allauth.org/en/latest/account/rate_limits.html
ACCOUNT_RATE_LIMITS = {
    # 5 fallidos por cuenta cada 15 minutos, más un tope por IP contra quien
    # prueba muchas cuentas a la vez. Un login correcto no borra el contador.
    "login_failed": env(
        "DJANGO_RATELIMIT_LOGIN_FAILED",
        default="10/m/ip,5/15m/key",
    ),
    "reset_password": env(
        "DJANGO_RATELIMIT_RESET_PASSWORD",
        default="20/m/ip,3/h/key",
    ),
    # Reenvío del correo de confirmación: conserva la espera de 3 minutos
    # entre envíos que trae allauth y le suma el tope por hora.
    "confirm_email": env(
        "DJANGO_RATELIMIT_CONFIRM_EMAIL",
        default="1/3m/key,3/h/key",
    ),
    "signup": env("DJANGO_RATELIMIT_SIGNUP", default="20/h/ip"),
}

# django-allauth headless
# -------------------------------------------------------------------------------
HEADLESS_ONLY = False
# El payload de usuario del login incluye rol, municipalidad y el flag de
# contraseña temporal, para que el panel decida el flujo sin una llamada extra.
HEADLESS_ADAPTER = "urbancheck.users.adapters.HeadlessAdapter"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24
# Link enviado en el correo de recuperación de contraseña.
# Se usa un https:// que apunta a la página web de reset de allauth (/accounts/...),
# porque los clientes de correo no rompen los enlaces https como sí ocurre con los
# esquemas custom (urbancheck://). El key de headless tiene el mismo formato que la
# URL web de allauth, así que funciona directamente en el navegador de cualquier
# dispositivo, sin depender de Expo Go ni de deep links.
# Configurable por entorno: en dev apuntar a la IP/LAN del backend, en prod al dominio.
# Por defecto (prod) usa el Universal Link /reset-password, que abre la app de
# UrbanCheck directamente cuando está instalada (ver config/deeplink.py) y cae en
# la web de allauth como fallback. En dev/Expo Go se sobreescribe por la URL web
# de allauth, porque los Universal Links no funcionan en Expo Go ni sobre una IP LAN.
ACCOUNT_RESET_PASSWORD_URL = env(
    "DJANGO_ACCOUNT_RESET_PASSWORD_URL",
    default="https://urbancheck.com.ar/reset-password?key={key}",
)
HEADLESS_FRONTEND_URLS = {
    "account_reset_password_from_key": ACCOUNT_RESET_PASSWORD_URL,
}

# Universal Links (iOS) / App Links (Android)
# -------------------------------------------------------------------------------
# Identificadores usados por los archivos de asociación servidos en
# /.well-known/ (ver config/deeplink.py). Completar al generar el build:
#   - IOS_UNIVERSAL_LINK_APP_ID: "<APPLE_TEAM_ID>.<bundleIdentifier>"
#   - ANDROID_SHA256_CERT_FINGERPRINTS: huella(s) SHA256 del certificado de firma
#     (se obtiene con `eas credentials` o `keytool`).
IOS_UNIVERSAL_LINK_APP_ID = env(
    "IOS_UNIVERSAL_LINK_APP_ID",
    default="TEAMID.com.anonymous.urbancheck",
)
ANDROID_APP_PACKAGE = env(
    "ANDROID_APP_PACKAGE",
    default="com.anonymous.urbancheck",
)
ANDROID_SHA256_CERT_FINGERPRINTS = env.list(
    "ANDROID_SHA256_CERT_FINGERPRINTS",
    default=[],
)

# Geocodificación (Nominatim / OpenStreetMap)
# -------------------------------------------------------------------------------
# Convierte direcciones escritas a mano en coordenadas. El servidor público es
# gratuito pero exige un User-Agent identificable con datos de contacto y un
# máximo de 1 req/seg. Para producción con volumen conviene self-hostear Nominatim
# y apuntar NOMINATIM_URL a esa instancia.
NOMINATIM_URL = env("NOMINATIM_URL", default="https://nominatim.openstreetmap.org/search")
NOMINATIM_REVERSE_URL = env(
    "NOMINATIM_REVERSE_URL",
    default="https://nominatim.openstreetmap.org/reverse",
)
NOMINATIM_USER_AGENT = env(
    "NOMINATIM_USER_AGENT",
    default="UrbanCheck/1.0 (contacto: stefano.riscaldino@yahoo.com)",
)
# Restringe los resultados a estos países (códigos ISO separados por coma). Vacío = global.
NOMINATIM_COUNTRYCODES = env("NOMINATIM_COUNTRYCODES", default="ar")

# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "allauth.headless.contrib.rest_framework.authentication.XSessionTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Solo lo declaramos como backend disponible: las vistas que filtran lo
    # activan explícitamente con ``filter_backends``. El feed ciudadano sigue
    # resolviendo sus filtros a mano (ver urbancheck/reports/api/filters.py).
    "DEFAULT_FILTER_BACKENDS": [],
    # El ``429`` en castellano y con código estable (``throttled``).
    "EXCEPTION_HANDLER": "urbancheck.common.throttling.api_exception_handler",
    # Límites por acción: las vistas eligen alcance en ``get_throttles`` (ver
    # ``urbancheck.common.throttling``). Por usuario; sin sesión, por IP.
    "DEFAULT_THROTTLE_RATES": {
        "reports": env("DJANGO_THROTTLE_REPORTS", default="20/hour"),
        "comments": env("DJANGO_THROTTLE_COMMENTS", default="60/hour"),
        "complaints": env("DJANGO_THROTTLE_COMPLAINTS", default="10/day"),
        "privacy_requests": env("DJANGO_THROTTLE_PRIVACY_REQUESTS", default="5/day"),
        # La página pública de un reporte compartido (US-030): sin sesión, por IP.
        "public_reports": env("DJANGO_THROTTLE_PUBLIC_REPORTS", default="120/hour"),
    },
    "NUM_PROXIES": NUM_PROXIES,
}

# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
CORS_URLS_REGEX = r"^/(api|_allauth)/.*$"

# By Default swagger ui is available only to admin user(s). You can change permission classes to change that
# See more configuration options at https://drf-spectacular.readthedocs.io/en/latest/settings.html#settings
SPECTACULAR_SETTINGS = {
    "TITLE": "UrbanCheck API",
    "DESCRIPTION": "Documentation of API endpoints of UrbanCheck",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "SCHEMA_PATH_PREFIX": "/api/",
    # Nombres propios para los catálogos que comparten nombre de campo
    # (``status``) o se usan en más de uno (``previous_status``): sin esto el
    # generador inventa nombres como ``Status614Enum``.
    "ENUM_NAME_OVERRIDES": {
        "ReportStatusEnum": "urbancheck.reports.models.Report.Status",
        "ComplaintStatusEnum": "urbancheck.reports.models.ReportComplaint.Status",
        "ComparisonStatusEnum": "urbancheck.reports.models.ResolutionComparison.Status",
        "AppealStatusEnum": "urbancheck.reports.models.ResolutionAppeal.Status",
        "ModerationOutcomeEnum": "urbancheck.reports.models.ModerationDecision.Outcome",
    },
}
# Your stuff...
# ------------------------------------------------------------------------------
