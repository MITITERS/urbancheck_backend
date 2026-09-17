from django.contrib import admin

from .models import Notification
from .models import NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "kind", "report", "is_read", "created_at"]
    list_filter = ["kind", "is_read"]
    search_fields = ["recipient__email", "message"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "kind", "enabled", "updated_at"]
    list_filter = ["kind", "enabled"]
    search_fields = ["user__email"]
