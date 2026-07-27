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
