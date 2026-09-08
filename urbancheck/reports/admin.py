"""Admin de los artefactos del circuito de cierre (US-046 y US-048).

Los dos van en **solo lectura**. La evidencia se crea cerrando un reporte desde
la app, con la verificación de proximidad y en la misma transacción que la
transición de estado; la apelación, apelando desde el detalle. Dejarlas
editables acá abriría por atrás justo lo que esos circuitos garantizan.
"""

from django.contrib import admin

from .models import ResolutionAppeal
from .models import ResolutionEvidence


class ReadOnlyAdmin(admin.ModelAdmin):
    """Se mira, no se toca."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ResolutionEvidence)
class ResolutionEvidenceAdmin(ReadOnlyAdmin):
    """Partes de trabajo de los operarios (US-046)."""

    list_display = ["report", "operational_area", "operator", "created_at"]
    list_filter = ["operational_area", "created_at"]
    search_fields = ["description"]


@admin.register(ResolutionAppeal)
class ResolutionAppealAdmin(ReadOnlyAdmin):
    """Objeciones de los ciudadanos a un cierre (US-048)."""

    list_display = ["report", "author", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["reason"]
