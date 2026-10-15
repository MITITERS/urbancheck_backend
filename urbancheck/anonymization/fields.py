"""Campo de modelo para las fotos que no se difuminan pero sí se sanean.

La foto de perfil no pasa por el circuito de US-041/US-042 —es la del propio
usuario, que eligió mostrarla—, pero el archivo que sube un celular trae GPS,
modelo del teléfono y fecha. El saneamiento va en el campo de **modelo** y no
en el serializer: así lo atraviesa toda carga, venga de la API, del admin de
Django o del shell.
"""

from __future__ import annotations

from django.db import models

from .service import strip_metadata


class MetadataFreeImageField(models.ImageField):
    """``ImageField`` que reescribe sin metadatos todo archivo nuevo."""

    def pre_save(self, model_instance, add):
        file = getattr(model_instance, self.attname)
        if file and not file._committed:  # noqa: SLF001 (lo mismo que mira Django)
            # Reasignar un ``File`` deja al descriptor envolviéndolo en un
            # ``FieldFile`` sin guardar, que ``super().pre_save`` escribe.
            setattr(model_instance, self.attname, strip_metadata(file))
        return super().pre_save(model_instance, add)
