"""Paginado del panel municipal."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class PanelPagination(PageNumberPagination):
    """Deja que el panel elija cuántas filas por página.

    El listado del panel es una herramienta de trabajo y cuántas filas conviene
    ver depende de quién mira y de qué está haciendo: revisar el día son pocas,
    barrer un mes son muchas. El tamaño lo elige el usuario con ``?page_size=``,
    no una constante del servidor.

    El tope existe porque el parámetro llega del cliente: sin él, un
    ``?page_size=100000`` se traduce en traer la tabla entera a memoria y
    serializarla, que es un problema de disponibilidad, no de gusto.
    """

    page_size_query_param = "page_size"
    max_page_size = 100
