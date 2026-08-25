"""Capa de acceso a datos acotada por jurisdicción (US-034).

La restricción se aplica una sola vez, acá, y no en cada vista: es lo que evita
que una consulta escrita en paralelo filtre datos entre municipios.
"""


class JurisdictionScopedMixin:
    """Acota el queryset de la vista a la municipalidad del usuario.

    Se apoya en ``super().get_queryset()``, así que una vista puede seguir
    definiendo ``queryset`` o su propio ``get_queryset()`` con anotaciones y
    ``select_related``, siempre que llame a ``super()``. El filtro se aplica
    después, al final de la cadena.

    Consecuencia buscada: pedir por ``id`` un recurso de otra jurisdicción
    devuelve ``404`` y no ``403``, porque el objeto directamente no existe para
    ese usuario. Un ``403`` confirmaría que el reporte existe.

    Toda vista nueva del panel tiene que heredar de este mixin.
    """

    def get_queryset(self):
        return super().get_queryset().for_user(self.request.user)
