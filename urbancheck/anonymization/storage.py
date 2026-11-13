"""Dónde espera la foto original mientras no está difuminada (US-042).

Con la publicación diferida la foto que sube el ciudadano no se difumina dentro
del request: se guarda tal cual y una tarea la procesa después. Entre esos dos
momentos existe en disco un archivo con rostros y patentes sin tapar, que es
exactamente lo que RN-11 no quiere que se publique.

Por eso no va al storage de siempre. El alias ``pending_photos`` apunta a un
lugar que **no se sirve**: está fuera de ``MEDIA_ROOT``, así que la ruta
``/media/`` de ``config/urls.py`` no lo alcanza, y se configura sin ``base_url``,
así que ``instance.photo_pending.url`` levanta ``ValueError`` en lugar de
devolver una dirección que alguien pueda abrir. Un serializer que exponga el
campo por descuido falla ruidosamente en vez de filtrar la original.

El archivo se borra apenas la tarea termina, salga bien o mal: una foto sin
difuminar no se conserva "por las dudas".
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import storages

#: Clave en ``settings.STORAGES``. En producción apunta a un prefijo privado,
#: sin lectura pública ni CDN (ver ``config/settings/production.py``).
PENDING_STORAGE_ALIAS = "pending_photos"


class PendingPhotoStorage(FileSystemStorage):
    """Storage privado cuya ubicación se lee de settings **en cada uso**.

    ``FileSystemStorage`` resuelve su directorio una sola vez y lo cachea, y un
    ``FileField`` resuelve su storage una sola vez al definirse la clase. Las
    dos cosas juntas dejan la ubicación congelada al importar el modelo, y eso
    tiene una consecuencia fea: un test que redirige el directorio a un
    temporal no lo consigue, y termina escribiendo fotos sin difuminar en el
    directorio real del proyecto, donde nadie las borra.

    Con ``base_location`` como propiedad viva, cambiar ``PENDING_PHOTO_ROOT``
    alcanza para mover el storage entero.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("file_permissions_mode", 0o600)
        kwargs.setdefault("directory_permissions_mode", 0o700)
        kwargs.pop("location", None)
        kwargs.pop("base_url", None)
        super().__init__(**kwargs)

    # django-stubs lo declara `str`; acá es `None` por diseño y esa es
    # justamente la diferencia que hace que `.url` falle.
    @property
    def base_url(self) -> str | None:  # type: ignore[override]
        """Sin URL, y por eso ``.url`` levanta ``ValueError``.

        Pasar ``base_url=None`` por configuración **no** alcanza:
        ``FileSystemStorage`` interpreta el ``None`` como "no configurado" y
        cae en ``MEDIA_URL``, que es justo la ruta que se sirve. La única forma
        de que no haya URL es que no la haya.
        """
        return None

    @property
    def base_location(self) -> str:
        return settings.PENDING_PHOTO_ROOT

    @property
    def location(self) -> str:
        return str(Path(self.base_location).resolve())


def pending_photo_storage():
    """El storage privado, resuelto al definir el campo.

    Es un callable y no la instancia porque las migraciones deconstruyen el
    campo por referencia: guardar la instancia congelaría la configuración del
    momento en que se generó la migración.
    """
    return storages[PENDING_STORAGE_ALIAS]


def pending_upload_to(instance, filename: str) -> str:
    """Ruta dentro del storage privado, separada por modelo.

    No lleva fecha: son archivos efímeros y agrupar por mes solo dejaría
    directorios vacíos detrás.
    """
    return f"pending/{instance._meta.model_name}/{filename}"  # noqa: SLF001
