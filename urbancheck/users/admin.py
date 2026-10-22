from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import TermsOfService
from .models import User

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


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


@admin.register(TermsOfService)
class TermsOfServiceAdmin(admin.ModelAdmin):
    """Publicación de los términos y condiciones (RN-10, C-23).

    Publicar una versión nueva hace que cada vecino la tenga que aceptar en su
    próximo ingreso. Una versión ya publicada no se edita: se publica otra.
    """

    list_display = ["version", "published_at"]
    ordering = ["-published_at"]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.published_at <= timezone.now():
            return ["version", "text", "published_at"]
        return []
