from django.contrib import admin

from .models import Municipality


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ["city", "province", "coverage_radius_km", "is_active", "created_at"]
    list_filter = ["is_active", "province"]
    search_fields = ["city", "province"]
