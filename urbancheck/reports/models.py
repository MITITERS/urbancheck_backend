from __future__ import annotations

from django.conf import settings
from django.db import models


class ReportQuerySet(models.QuerySet):
    """Consultas de reportes acotadas por jurisdicción (US-034).

    Es la única puerta de entrada de las vistas del panel: si una consulta no
    pasa por acá, puede filtrar datos entre municipios. El mixin
    ``JurisdictionScopedMixin`` de la capa de API existe para que ninguna vista
    nueva pueda saltearla por olvido.
    """

    def for_user(self, user) -> ReportQuerySet:
        """Reportes sobre los que ``user`` puede operar desde el panel o la app.

        Un usuario sin municipalidad —ciudadano, o administrador de la
        plataforma, que no está acotado a ningún municipio— no gestiona reportes
        de nadie: devolvemos vacío en lugar de todo. El default seguro importa,
        porque este método se usa desde vistas que todavía no existen.
        """
        municipality_id = getattr(user, "municipality_id", None)
        if not municipality_id:
            return self.none()
        return self.filter(municipality_id=municipality_id)


class Report(models.Model):
    class Category(models.TextChoices):
        BACHE = "bache", "Bache"
        ALUMBRADO = "alumbrado", "Alumbrado"
        BASURA = "basura", "Basura"
        SEMAFORO = "semaforo", "Semáforo"
        VEREDA = "vereda", "Vereda"
        OTRO = "otro", "Otro"

    class Status(models.TextChoices):
        PENDIENTE_VALIDACION = "pendiente_validacion", "Pendiente de validación"
        REPORTADO = "reportado", "Reportado"
        EN_PROCESO = "en_proceso", "En proceso"
        RESUELTO = "resuelto", "Resuelto"
        CANCELADO = "cancelado", "Cancelado"
        ARCHIVADO = "archivado", "Archivado"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    # Jurisdicción del reporte (US-034). Se asigna al crearlo y no se
    # modifica: ningún serializer la expone como campo editable.
    municipality = models.ForeignKey(
        "municipalities.Municipality",
        on_delete=models.PROTECT,
        related_name="reports",
    )
    photo = models.ImageField(upload_to="reports/%Y/%m/")
    description = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDIENTE_VALIDACION,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Última edición hecha por el autor. Se diferencia de ``updated_at`` (que se
    # mueve con cualquier guardado, incluido un cambio de estado municipal) para
    # poder mostrar "editado el ..." solo cuando el ciudadano tocó el contenido.
    edited_at = models.DateTimeField(null=True, blank=True)

    # El autor solo puede modificar o borrar su reporte mientras el municipio no
    # empezó a gestionarlo.
    EDITABLE_STATUSES = frozenset(
        {Status.PENDIENTE_VALIDACION, Status.REPORTADO},
    )

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.category} — {self.author} ({self.status})"

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES


class ReportStatusHistory(models.Model):
    """Traza de cada cambio de estado (US-013).

    Se escribe en la misma transacción que el cambio, así que no puede quedar un
    reporte con un estado nuevo y sin registro de quién lo movió.
    """

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    # Estado resultante. ``previous_status`` queda nulo en el alta del reporte,
    # que es el único asiento del historial sin estado anterior.
    status = models.CharField(max_length=30, choices=Report.Status.choices)
    previous_status = models.CharField(
        max_length=30,
        choices=Report.Status.choices,
        blank=True,
        default="",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # Obligatorio en las transiciones que lo exigen (cancelar, rechazar).
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.report_id}: {self.previous_status or '—'} → {self.status}"


class Comment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Like(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="likes",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "user"], name="unique_report_like")
        ]
