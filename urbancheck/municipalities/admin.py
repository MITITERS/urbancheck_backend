from django.contrib import admin

from .models import Municipality


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
