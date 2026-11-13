"""Manejo de archivos subidos sin tocar el disco (US-041, escenario 6)."""

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import MemoryFileUploadHandler


class MemoryOnlyUploadHandler(MemoryFileUploadHandler):
    """Toda carga se recibe en memoria; nunca en un temporal a disco.

    Por defecto Django pasa a ``TemporaryFileUploadHandler`` cualquier archivo
    de más de 2,5 MB, y una foto de celular casi siempre lo es: la original sin
    anonimizar quedaría en ``/tmp`` mientras dura el request. Acá no hay
    segundo handler. Lo que supera ``FILE_UPLOAD_MAX_MEMORY_SIZE`` se rechaza
    entero con un 400, antes de leer el cuerpo, en vez de acumularlo en RAM.
    """

    def handle_raw_input(
        self,
        input_data,
        META,  # noqa: N803 — la firma la define Django.
        content_length,
        boundary,
        encoding=None,
    ):
        if content_length > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
            msg = "La carga supera el tamaño máximo permitido."
            raise RequestDataTooBig(msg)
        self.activated = True
