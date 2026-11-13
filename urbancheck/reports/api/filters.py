"""Filtros y búsqueda del feed de reportes (US-006 y US-020).

Se resuelven a mano sobre el queryset en vez de sumar ``django-filter``: el juego
de filtros es chico y estable, y evitamos una dependencia más en el proyecto.
"""

import unicodedata

from django.db.models import Q

from urbancheck.reports.models import Report

# Largo mínimo de término de búsqueda; por debajo de esto la consulta devolvería
# prácticamente todo el feed y no aporta nada.
MIN_SEARCH_LENGTH = 2


def _strip_accents(text: str) -> str:
    """Normaliza para comparar sin tildes: "semáforo" y "semaforo" son lo mismo."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _split_csv(raw: str | None) -> list[str]:
    """``"bache,basura"`` -> ``["bache", "basura"]``."""
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _categories_matching(term: str) -> list[str]:
    """Categorías cuyo valor o etiqueta contiene ``term`` (sin distinguir tildes).

    Permite que buscar "semáforo" o "Semaforo" encuentre los reportes de esa
    categoría aunque el texto no aparezca en la descripción.
    """
    needle = _strip_accents(term).casefold()
    return [
        value
        for value, label in Report.Category.choices
        if needle in _strip_accents(value).casefold()
        or needle in _strip_accents(label).casefold()
    ]


def _statuses_matching(term: str) -> list[str]:
    needle = _strip_accents(term).casefold()
    return [
        value
        for value, label in Report.Status.choices
        if needle in _strip_accents(value).casefold()
        or needle in _strip_accents(label).casefold()
    ]


def apply_report_filters(queryset, query_params, *, requesting_user=None):
    """Aplica ``category``, ``status``, ``search`` y ``author``.

    ``category`` y ``status`` aceptan varios valores separados por coma
    (``?category=bache,basura``). Los valores desconocidos se ignoran en vez de
    provocar un 400: el feed nunca debe romperse por un parámetro mal escrito.
    """
    valid_categories = set(Report.Category.values)
    categories = [
        c for c in _split_csv(query_params.get("category")) if c in valid_categories
    ]
    if categories:
        queryset = queryset.filter(category__in=categories)

    valid_statuses = set(Report.Status.values)
    statuses = [
        s for s in _split_csv(query_params.get("status")) if s in valid_statuses
    ]
    if statuses:
        queryset = queryset.filter(status__in=statuses)

    author = query_params.get("author")
    if author and author.isdigit():
        author_id = int(author)
        queryset = queryset.filter(author_id=author_id)
        # US-027: un perfil privado no expone su listado de reportes a terceros.
        is_own_profile = requesting_user is not None and requesting_user.id == author_id
        if not is_own_profile:
            queryset = queryset.filter(author__is_public=True)

    search = (query_params.get("search") or query_params.get("q") or "").strip()
    if len(search) >= MIN_SEARCH_LENGTH:
        # Palabra clave: descripción; zona: dirección geocodificada. Además se
        # traduce el término a categorías/estados para que buscar "bache" o
        # "resuelto" funcione aunque no aparezcan en el texto libre.
        condition = Q(description__icontains=search) | Q(address__icontains=search)
        matched_categories = _categories_matching(search)
        if matched_categories:
            condition |= Q(category__in=matched_categories)
        matched_statuses = _statuses_matching(search)
        if matched_statuses:
            condition |= Q(status__in=matched_statuses)
        queryset = queryset.filter(condition)

    return queryset
