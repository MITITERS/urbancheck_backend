from django.contrib import admin

from .models import Municipality
from .models import OperationalArea


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ["city", "province", "boundary_points", "is_active", "created_at"]
    list_filter = ["is_active", "province"]
    search_fields = ["city", "province"]

    @admin.display(description="Vértices del límite")
    def boundary_points(self, obj: Municipality) -> str:
        """Cuántos puntos tiene el polígono, o que no tiene ninguno.

        El polígono en crudo es una lista de cientos de pares de coordenadas:
        en una columna de listado no dice nada. Lo único accionable desde acá
        es si el municipio tiene límite trazado o no.
        """
        return str(len(obj.boundary)) if obj.has_coverage else "sin límite"


@admin.register(OperationalArea)
class OperationalAreaAdmin(admin.ModelAdmin):
    """Áreas operativas (US-039).

    Sin acción de borrado: el área se desactiva, igual que en la API. Dejarla
    borrable desde acá abriría por atrás justo lo que la API cierra.
    """

    list_display = ["name", "municipality", "contact_email", "contact_phone", "is_active"]
    list_filter = ["is_active", "municipality"]
    search_fields = ["name", "contact_email"]

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
