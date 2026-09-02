from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db import transaction

from urbancheck.reports.geo import polygon_bounds


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

    def covered_by(self, municipality) -> ReportQuerySet:
        """Reportes del municipio que además caen dentro de su área de cobertura.

        Pertenecer no alcanza para responder "lo que pasa a mi alrededor". Hay
        reportes que apuntan a un municipio y están a decenas de kilómetros: los
        cargados antes de que existiera la cobertura, y los que cayeron en el
        respaldo de ``ACTIVE_MUNICIPALITY_ID`` por no tener coordenadas al
        crearse. Un reporte creado hoy cumple las dos condiciones por
        construcción —la creación rechaza lo que queda fuera de cobertura—, así
        que esta segunda condición solo saca lo que nunca debió estar ahí.

        Los reportes **sin coordenadas** se quedan: no hay dónde ubicarlos, y su
        único vínculo con un municipio es el que ya tienen.

        Filtra por el **recuadro** del polígono, no por el polígono exacto. Sin
        PostGIS no hay forma de expresar punto-en-polígono en SQL, y traer todo
        a Python para filtrarlo rompería la pereza del queryset, que después se
        pagina. El recuadro alcanza de sobra para lo que esto hace: sacar de
        encima reportes que están a decenas de kilómetros. Un reporte dentro del
        recuadro pero fuera del límite se cuela, y es un caso que solo puede
        existir entre los datos viejos —la creación de hoy rechaza cualquier
        punto fuera del polígono—.
        """
        queryset = self.filter(municipality=municipality)
        if not municipality.has_coverage:
            return queryset
        min_lat, min_lng, max_lat, max_lng = polygon_bounds(municipality.boundary)
        return queryset.filter(
            models.Q(latitude__isnull=True)
            | models.Q(longitude__isnull=True)
            | models.Q(
                latitude__gte=min_lat,
                latitude__lte=max_lat,
                longitude__gte=min_lng,
                longitude__lte=max_lng,
            ),
        )


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
    # Número del reporte **dentro de su municipalidad**, que es como lo nombran
    # el vecino y el municipio: "el reporte 12 de Villa María". El id de la base
    # sigue siendo la clave técnica y es lo que viaja en las URLs; este número es
    # el identificador de cara al usuario. Se asigna al crear y no cambia nunca.
    #
    # La secuencia sale del máximo entregado en ese municipio. Consecuencia
    # asumida: si se borra el último reporte, el próximo recibe ese número. Solo
    # puede pasar con el más reciente y solo el autor puede borrarlo, mientras el
    # municipio todavía no lo tomó. La alternativa —un contador persistente en
    # ``Municipality``— tiene un problema peor: cualquier ``save()`` sobre una
    # instancia leída antes del alta lo rebobina, y el número se repite en
    # silencio hasta chocar contra la restricción de unicidad.
    number = models.PositiveIntegerField(null=True, blank=True, editable=False)
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

    # El autor solo puede modificar o borrar su reporte mientras nadie más lo
    # miró: es decir, hasta que un validador lo confirma en terreno.
    #
    # ``REPORTADO`` salió de esta lista a propósito. Un reporte validado ya pasó
    # por el trabajo de otra persona y entró en la cola del municipio: dejar que
    # el autor le cambie la categoría o la dirección después de eso invalida esa
    # validación sin que nadie se entere.
    EDITABLE_STATUSES = frozenset({Status.PENDIENTE_VALIDACION})

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["municipality", "number"],
                name="unique_report_number_per_municipality",
            ),
        ]

    def __str__(self):
        return f"{self.category} — {self.author} ({self.status})"

    def save(self, *args, **kwargs):
        """Asigna el número de municipio la primera vez que se guarda.

        Va en ``save()`` y no en la vista para que lo tengan todos los caminos de
        alta —la API, el seed de demo, las factories de los tests—: uno que se
        olvidara dejaría un reporte sin número y la pantalla mostrando un hueco.

        El bloqueo sobre la fila de la municipalidad serializa las altas de ese
        municipio. Sin él, dos altas simultáneas leen el mismo máximo y la
        segunda choca contra la restricción de unicidad. Es un candado corto y
        por municipio: no frena las altas de los demás.
        """
        if self.number is None and self.municipality_id is not None:
            # Import local: a nivel de módulo sería una dependencia circular.
            from urbancheck.municipalities.models import Municipality  # noqa: PLC0415

            with transaction.atomic():
                # La fila del municipio se usa solo como candado: es lo único
                # que existe siempre y que todas las altas de ese municipio
                # comparten.
                Municipality.objects.select_for_update().get(pk=self.municipality_id)
                self.number = self._next_number_for(self.municipality_id)
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    @staticmethod
    def _next_number_for(municipality_id: int) -> int:
        last = Report.objects.filter(municipality_id=municipality_id).aggregate(
            last=models.Max("number"),
        )["last"]
        return (last or 0) + 1

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
