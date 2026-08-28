"""Filtros del listado del panel municipal (US-012).

Se resuelven con ``django-filter`` porque el juego es grande: selección
múltiple, rango de fechas y ordenamiento. El feed ciudadano sigue con sus
filtros a mano en ``filters.py``, que responden a otra pregunta.

Los filtros se combinan con AND entre sí y con OR dentro de una misma selección
múltiple.

``municipality`` es para el administrador de la plataforma, que ve todas las
jurisdicciones y necesita poder acotar. **No es un agujero en la jurisdicción**:
el filtro se aplica sobre el queryset que ya devolvió
``JurisdictionScopedMixin``, así que un agente que lo pida con un municipio
ajeno recibe una lista vacía, no la del otro municipio.
"""

from django_filters import rest_framework as filters

from urbancheck.reports.models import Report


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Acepta ``?status=reportado,en_proceso`` (OR dentro del filtro)."""


class PanelReportFilterSet(filters.FilterSet):
    municipality = filters.NumberFilter(field_name="municipality_id")
    # Todo lo que reportó una persona, para el perfil que abre el panel desde
    # su nombre. Como el resto, se aplica sobre el queryset ya acotado por
    # jurisdicción: un agente ve lo que esa persona reportó **en su municipio**,
    # nunca su actividad en otro.
    author = filters.NumberFilter(field_name="author_id")
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
        fields = [
            "municipality",
            "author",
            "status",
            "category",
            "created_from",
            "created_to",
            "zone",
        ]
