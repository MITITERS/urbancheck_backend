"""Filtros del listado del panel municipal (US-012).

Se resuelven con ``django-filter`` porque el juego es grande: selección
múltiple, rango de fechas y ordenamiento. El feed ciudadano sigue con sus
filtros a mano en ``filters.py``, que responden a otra pregunta.

Los filtros se combinan con AND entre sí y con OR dentro de una misma selección
múltiple. Ninguno acepta municipio: la jurisdicción la resuelve el servidor.
"""

from django_filters import rest_framework as filters

from urbancheck.reports.models import Report


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Acepta ``?status=reportado,en_proceso`` (OR dentro del filtro)."""


class PanelReportFilterSet(filters.FilterSet):
    status = CharInFilter(field_name="status", lookup_expr="in")
    category = CharInFilter(field_name="category", lookup_expr="in")
    created_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    # "Zona" no existe como entidad en el modelo y nadie la definió: se resuelve
    # como búsqueda de texto sobre la dirección. Decisión documentada en el
    # README; no se implementa filtrado por polígonos.
    zone = filters.CharFilter(field_name="address", lookup_expr="icontains")

    ordering = filters.OrderingFilter(
        fields=(
            ("created_at", "created_at"),
            ("like_count", "like_count"),
        ),
    )

    class Meta:
        model = Report
        fields = ["status", "category", "created_from", "created_to", "zone"]
