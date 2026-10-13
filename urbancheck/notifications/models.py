from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Aviso dirigido a un usuario concreto.

    El modelo es genérico a propósito: ``kind`` describe qué pasó y ``report``
    apunta al reporte involucrado, de modo que el cliente puede navegar al detalle
    sin necesitar un endpoint por tipo de aviso.
    """

    class Kind(models.TextChoices):
        NUEVO_COMENTARIO = "nuevo_comentario", "Nuevo comentario"
        CAMBIO_ESTADO = "cambio_estado", "Cambio de estado"
        NUEVO_LIKE = "nuevo_like", "Nuevo like"
        # La comunicación institucional del municipio sobre un reporte
        # (US-024). Es un tipo propio y no un cambio de estado porque no lo es:
        # el reporte sigue donde estaba y lo que cambió es que el municipio se
        # pronunció.
        RESPUESTA_OFICIAL = "respuesta_oficial", "Respuesta oficial"
        # Aviso previo al archivado automático (US-031). Va siete días antes,
        # para que el vecino tenga margen de conseguir la interacción que falta.
        PROXIMO_ARCHIVADO = "proximo_archivado", "Reporte por archivarse"
        # Aviso previo al vencimiento de la ventana de objeción (US-047).
        PROXIMA_CONFIRMACION = "proxima_confirmacion", "Cierre por confirmarse"
        # Le llega al agente de la jurisdicción y al operario que cerró cuando
        # el ciudadano apela (US-048). Es el único aviso que **no** va al autor
        # del reporte: acá el autor es quien lo dispara.
        APELACION_CIERRE = "apelacion_cierre", "Cierre apelado"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    # Quien disparó el aviso. Nulo cuando lo genera el sistema.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_sent",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    report = models.ForeignKey(
        "reports.Report",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    message = models.CharField(max_length=255)
    # Detalle del cambio de estado (US-011). Vacío en los avisos sociales, que
    # no tienen transición asociada.
    # 40 por lo mismo que en ``Report.status``: el estado más largo mide 31.
    previous_status = models.CharField(max_length=40, blank=True, default="")
    new_status = models.CharField(max_length=40, blank=True, default="")
    reason = models.TextField(blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Nombre explícito: la bandeja se consulta siempre por
            # destinatario + leídas.
            models.Index(
                fields=["recipient", "is_read"],
                name="notif_recipient_read_idx",
            ),
        ]

    def __str__(self):
        return f"{self.kind} → {self.recipient}"


class NotificationPreference(models.Model):
    """Preferencia de un usuario sobre un tipo de aviso (US-025).

    Un registro por tipo y no un booleano por columna: agregar un tipo nuevo al
    catálogo no requiere migrar el esquema.

    **Default: todo activado.** Un usuario sin preferencias registradas recibe
    todo, así que la ausencia de fila significa "habilitado".

    Qué desactiva: **solo el push**. La notificación igual queda en la bandeja.
    Es el comportamiento menos sorpresivo y el que menos riesgo tiene de que el
    vecino se pierda información de su propio reclamo.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    kind = models.CharField(max_length=30, choices=Notification.Kind.choices)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind"],
                name="unique_notification_preference",
            ),
        ]
        ordering = ["kind"]

    def __str__(self) -> str:
        return f"{self.user}: {self.kind} = {self.enabled}"

    @classmethod
    def is_enabled(cls, user, kind: str) -> bool:
        """Única consulta de preferencia del sistema."""
        preference = cls.objects.filter(user=user, kind=kind).first()
        return True if preference is None else preference.enabled
