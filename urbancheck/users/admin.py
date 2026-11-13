from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from urbancheck.common.admin_login import limit_admin_login

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User

# El login del admin con el mismo límite de intentos que el de la API (N-02).
admin.site.login = limit_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name", "phone", "avatar", "is_public")}),
        (
            _("Work account"),
            {
                "fields": (
                    "role",
                    "municipality",
                    "operational_area",
                    "is_work_account_active",
                    "must_change_password",
                ),
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (
            _("Important dates"),
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "terms_version",
                    "terms_accepted_at",
                ),
            },
        ),
    )
    # La aceptación de los términos la registra el propio vecino (RN-10): el
    # admin la muestra, pero no la puede inventar.
    readonly_fields = ["terms_version", "terms_accepted_at"]
    list_display = ["email", "name", "role", "municipality", "is_superuser"]
    list_filter = ["role", "municipality"]
    search_fields = ["name", "email"]
    ordering = ["id"]
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
