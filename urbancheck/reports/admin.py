"""Admin de los artefactos del circuito de cierre (US-046 y US-048) y de las
denuncias (US-021 y US-043).

Los dos van en **solo lectura**. La evidencia se crea cerrando un reporte desde
la app, con la verificación de proximidad y en la misma transacción que la
transición de estado; la apelación, apelando desde el detalle. Dejarlas
editables acá abriría por atrás justo lo que esos circuitos garantizan.
"""

from django.contrib import admin
from django.contrib import messages
from django.utils import timezone

from .models import Comment
from .models import Like
from .models import OfficialResponse
from .models import Report
from .models import ReportAreaAssignment
from .models import ReportComplaint
from .models import ReportStatusHistory
from .models import ResolutionAppeal
from .models import ResolutionComparison
from .models import ResolutionEvidence
from .privacy import ComplaintAlreadyResolvedError
from .privacy import deadline_for
from .privacy import dismiss
from .privacy import remove_image
from .privacy import review_window


class ReadOnlyAdmin(admin.ModelAdmin):
    """Se mira, no se toca."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class OverdueFilter(admin.SimpleListFilter):
    """Las solicitudes por dato personal que pasaron el plazo (US-043, E7)."""

    title = "plazo"
    parameter_name = "plazo"

    def lookups(self, request, model_admin):
        return [("vencidas", "Fuera de plazo"), ("en_plazo", "En plazo")]

    def queryset(self, request, queryset):
        limit = timezone.now() - review_window()
        pending = queryset.filter(status=ReportComplaint.Status.PENDIENTE)
        if self.value() == "vencidas":
            return pending.filter(created_at__lt=limit)
        if self.value() == "en_plazo":
            return pending.filter(created_at__gte=limit)
        return queryset


@admin.register(ReportComplaint)
class ReportComplaintAdmin(ReadOnlyAdmin):
    """Denuncias (US-021, US-043).

    Las de dato personal se resuelven acá o desde la bandeja del panel: las dos
    llaman a los mismos servicios de ``privacy.py`` (``remove_image`` y
    ``dismiss``), que borran el archivo, devuelven la visibilidad y avisan a
    quien corresponde. Nunca se edita el estado a mano: marcarla resuelta sin
    pasar por el servicio dejaría la imagen publicada.

    Las de contenido (US-021) son del agente municipal (US-049) y acá solo se
    miran.
    """

    list_display = [
        "report",
        "reason",
        "image",
        "status",
        "reporter",
        "created_at",
        "deadline",
        "overdue",
        "resolved_at",
        "resolved_by",
    ]
    list_filter = ["reason", "status", OverdueFilter, "created_at"]
    list_select_related = ["report", "reporter", "resolved_by"]
    # La más vieja primero: es la que está más cerca de vencer (escenario 4).
    ordering = ["created_at"]
    actions = ["remove_selected_images", "dismiss_selected_requests"]

    @admin.display(description="imagen")
    def image(self, obj) -> str:
        if obj.reason not in ReportComplaint.PLATFORM_REASONS:
            return "-"
        labels = {
            "report": "foto del reporte",
            "resolution_evidence": "foto del cierre",
            "resolution_appeal": "foto de la objeción",
        }
        return labels[obj.image_kind]

    @admin.display(description="vence")
    def deadline(self, obj):
        if obj.reason not in ReportComplaint.PLATFORM_REASONS:
            return None
        return deadline_for(obj)

    @admin.display(description="fuera de plazo", boolean=True)
    def overdue(self, obj) -> bool | None:
        if obj.reason not in ReportComplaint.PLATFORM_REASONS or not obj.is_pending:
            return None
        return timezone.now() > deadline_for(obj)

    def has_resolve_permission(self, request) -> bool:
        """Las resuelve el administrador de la plataforma (US-043, E10)."""
        user = request.user
        return user.is_superuser or user.is_platform_admin

    @admin.action(
        description="Eliminar la imagen denunciada",
        permissions=["resolve"],
    )
    def remove_selected_images(self, request, queryset):
        self._resolve(request, queryset, remove_image, "con la imagen eliminada")

    @admin.action(
        description="Desestimar (la imagen no muestra datos personales)",
        permissions=["resolve"],
    )
    def dismiss_selected_requests(self, request, queryset):
        self._resolve(request, queryset, dismiss, "desestimadas")

    def _resolve(self, request, queryset, service, outcome: str) -> None:
        pending = queryset.filter(
            reason__in=ReportComplaint.PLATFORM_REASONS,
            status=ReportComplaint.Status.PENDIENTE,
        )
        done = 0
        for complaint in pending:
            try:
                service(complaint, admin=request.user)
            except ComplaintAlreadyResolvedError:
                # Otra solicitud sobre el mismo archivo la cerró en esta misma
                # tanda, o la resolvió otro administrador.
                continue
            done += 1
        skipped = queryset.count() - done
        message = f"{done} solicitudes {outcome}."
        if skipped:
            message += (
                f" {skipped} no se tocaron: ya estaban resueltas o no son de "
                "dato personal."
            )
        self.message_user(request, message, messages.SUCCESS)


@admin.register(ResolutionEvidence)
class ResolutionEvidenceAdmin(ReadOnlyAdmin):
    """Partes de trabajo de los operarios (US-046)."""

    list_display = ["report", "operational_area", "operator", "created_at"]
    list_filter = ["operational_area", "created_at"]
    search_fields = ["description"]


@admin.register(ResolutionComparison)
class ResolutionComparisonAdmin(ReadOnlyAdmin):
    """Registro de las comparaciones automáticas de cierres (US-015, escenario 9).

    Es el lugar de auditoría: fecha, veredicto, explicación y modelo de cada
    comparación, incluidas las que terminaron sin veredicto y por qué.
    """

    list_display = [
        "evidence",
        "status",
        "verdict",
        "model_name",
        "attempts",
        "requested_at",
        "completed_at",
    ]
    list_filter = ["status", "verdict", "model_name"]
    search_fields = ["explanation"]


@admin.register(ResolutionAppeal)
class ResolutionAppealAdmin(ReadOnlyAdmin):
    """Objeciones de los ciudadanos a un cierre (US-048)."""

    list_display = ["report", "author", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["reason"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "number",
        "category",
        "status",
        "municipality",
        "author",
        "created_at",
    ]
    list_filter = ["status", "category", "municipality"]
    search_fields = ["description", "address", "author__email"]
    list_display += ["photo_status"]
    list_filter += ["photo_status"]
    # La foto solo entra por la API, que la manda a difuminar (US-041/US-042).
    # Un formulario del admin la guardaría tal cual se subió, y el estado de
    # procesamiento a mano publicaría una imagen que nunca pasó por el servicio.
    readonly_fields = [
        "photo",
        "photo_pending",
        "photo_status",
        "photo_attempts",
        "photo_failed_at",
    ]

    def get_deleted_objects(self, objs, request):
        """El superusuario borra el reporte con todo lo que cuelga de él.

        Historial, asignaciones, evidencias y apelaciones son de solo lectura
        sueltos, y eso haría que Django bloquee el borrado en cascada.
        """
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request,
        )
        if request.user.is_superuser:
            perms_needed = set()
        return deleted, model_count, perms_needed, protected


@admin.register(ReportStatusHistory)
class ReportStatusHistoryAdmin(ReadOnlyAdmin):
    list_display = [
        "report",
        "previous_status",
        "status",
        "changed_by",
        "origin",
        "created_at",
    ]
    list_filter = ["status", "origin"]


@admin.register(ReportAreaAssignment)
class ReportAreaAssignmentAdmin(ReadOnlyAdmin):
    list_display = ["report", "previous_area", "area", "assigned_by", "created_at"]
    list_filter = ["area"]


@admin.register(OfficialResponse)
class OfficialResponseAdmin(admin.ModelAdmin):
    list_display = ["report", "municipality", "author", "created_at"]
    list_filter = ["municipality"]
    search_fields = ["text"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["report", "author", "created_at"]
    search_fields = ["text", "author__email"]


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ["report", "user", "created_at"]
