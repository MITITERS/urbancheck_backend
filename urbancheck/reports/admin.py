"""Admin de los artefactos del circuito de cierre (US-046 y US-048).

Los dos van en **solo lectura**. La evidencia se crea cerrando un reporte desde
la app, con la verificación de proximidad y en la misma transacción que la
transición de estado; la apelación, apelando desde el detalle. Dejarlas
editables acá abriría por atrás justo lo que esos circuitos garantizan.
"""

from django.contrib import admin

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


class ReadOnlyAdmin(admin.ModelAdmin):
    """Se mira, no se toca."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ReportComplaint)
class ReportComplaintAdmin(ReadOnlyAdmin):
    """Denuncias (US-021, US-043). Se resuelven desde el panel, que borra el
    archivo; marcarlas resueltas acá dejaría la imagen publicada."""

    list_display = [
        "report",
        "reason",
        "status",
        "reporter",
        "created_at",
        "resolved_at",
        "resolved_by",
    ]
    list_filter = ["reason", "status", "created_at"]


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
    list_display = ["id", "number", "category", "status", "municipality", "author", "created_at"]
    list_filter = ["status", "category", "municipality"]
    search_fields = ["description", "address", "author__email"]
    list_display += ["photo_status"]  # noqa: RUF005 (se lee como continuación)
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
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        if request.user.is_superuser:
            perms_needed = set()
        return deleted, model_count, perms_needed, protected


@admin.register(ReportStatusHistory)
class ReportStatusHistoryAdmin(ReadOnlyAdmin):
    list_display = ["report", "previous_status", "status", "changed_by", "origin", "created_at"]
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
