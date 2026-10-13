from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db import transaction

from urbancheck.anonymization.models import PendingPhotoMixin
from urbancheck.anonymization.models import PhotoStatus
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

    # Visibilidad pública
    # --------------------------------------------------------------------------
    # **Única** definición de qué reporte puede ver un tercero. Las condiciones
    # se suman acá y en ningún otro lado: un filtro escrito aparte en una vista
    # es un filtro que otra vista se olvida de copiar. US-042 sumó la suya
    # —``photo_ready``, la imagen todavía en procesamiento— junto a
    # ``on_privacy_hold``.

    def publicly_visible(self) -> ReportQuerySet:
        """Lo que se lista en el feed, el mapa y el perfil público.

        Cuatro condiciones: que el reporte siga siendo un problema activo
        (US-013), que no esté retenido por una solicitud de protección de datos,
        que no se haya retirado por una (US-043) y que su imagen ya esté
        difuminada (US-042). Un reporte existe desde que el ciudadano lo envía,
        pero no es público hasta que su foto pasó por el servicio.
        """
        return (
            self.exclude(status__in=Report.INACTIVE_PUBLIC_STATUSES)
            .exclude(on_privacy_hold())
            .filter(photo_removed_at__isnull=True)
            .filter(photo_ready())
        )

    def visible_to(self, user) -> ReportQuerySet:
        """Lo que ``user`` puede abrir por id: el detalle y lo que cuelga de él.

        Es más ancho que ``publicly_visible`` en una sola cosa: los estados
        inactivos se abren igual, porque es a donde lleva la notificación del
        cambio de estado. La protección de datos **no** se afloja —ni la
        retención mientras se revisa ni el retiro definitivo—, salvo para el
        autor, que sigue viendo su propio reclamo marcado como en revisión o
        retirado: ocultarle su propio reporte no protege a nadie.

        Con la imagen en procesamiento (US-042) vale lo mismo y por la misma
        razón: para cualquier tercero el reporte todavía no existe y el detalle
        responde 404, pero el autor abre el suyo y ve que se está procesando.
        """
        return self.filter(
            models.Q(author_id=user.pk)
            | (
                ~on_privacy_hold()
                & models.Q(photo_removed_at__isnull=True)
                & photo_ready()
            ),
        )


def photo_ready() -> models.Q:
    """Si la imagen del reporte ya está difuminada y por lo tanto publicable.

    Es la condición de US-042, y se evalúa sobre la foto y no sobre el estado
    del reporte: la máquina de estados de US-013 no se toca. Un reporte en
    ``pendiente`` o en ``fallida`` es invisible para todos menos su autor y el
    panel municipal, que lo ve sin foto y no puede publicarlo.
    """
    return models.Q(photo_status=PhotoStatus.PROCESADA)


def on_privacy_hold() -> models.Exists:
    """Si el reporte tiene una solicitud por dato personal sin resolver (US-043).

    Es la única excepción al principio de que una denuncia no altera por sí sola
    la visibilidad: basta **una** solicitud, sin umbral. Se oculta primero y se
    revisa después, porque el costo es asimétrico: unas horas de invisibilidad
    de un reclamo contra la exposición del rostro de alguien que nunca consintió
    aparecer.

    Se deduce de las solicitudes pendientes en lugar de guardarse como marca en
    el reporte: una marca aparte hay que acordarse de apagarla en cada camino
    que resuelve, y una que queda prendida esconde un reporte para siempre.
    """
    return models.Exists(
        ReportComplaint.objects.filter(
            report=models.OuterRef("pk"),
            status=ReportComplaint.Status.PENDIENTE,
            reason__in=ReportComplaint.HIDING_REASONS,
        ),
    )


class Report(PendingPhotoMixin, models.Model):
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
        # Estado intermedio introducido por US-046: el operario cierra el
        # trabajo, pero el cierre no es definitivo hasta que el autor deja
        # pasar la ventana de objeción (US-047) o la agota apelando (US-048).
        # Existe porque quien ejecuta el trabajo no puede ser también quien
        # certifica sin contraparte que quedó bien hecho.
        RESUELTO_PENDIENTE = (
            "resuelto_pendiente_confirmacion",
            "Resuelto pendiente de confirmación",
        )
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
    # Obligatoria al crear —lo exige el serializer de alta—, pero puede quedar
    # vacía: el administrador la elimina si expone un dato personal (US-043).
    photo = models.ImageField(upload_to="reports/%Y/%m/", blank=True)
    # Cuándo se retiró la foto por protección de datos (US-043), y con ella **el
    # reporte entero**: un reporte sin foto no se vuelve a publicar nunca. Es la
    # marca que lee ``publicly_visible``. El autor lo sigue viendo como retirado
    # y el municipio en el panel; nadie más.
    photo_removed_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    # Área operativa que se hizo cargo del reporte (US-028). Se asigna en la
    # misma transacción que el paso a *En proceso* y no se puede quitar: un
    # reporte en gestión siempre tiene un responsable operativo.
    #
    # ``PROTECT`` porque las áreas no se borran, se desactivan: el vínculo
    # histórico tiene que sobrevivir a la baja de la dependencia.
    operational_area = models.ForeignKey(
        "municipalities.OperationalArea",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reports",
    )
    # Cuándo entró el reporte a la bandeja del área. Es el orden de trabajo del
    # operario (US-045): primero lo más demorado. Se guarda denormalizado en vez
    # de leerlo del registro de asignaciones porque la bandeja ordena por él, y
    # ordenar por una subconsulta en cada carga de pantalla no se paga.
    area_assigned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        # 40 y no 30: ``resuelto_pendiente_confirmacion`` mide 31 caracteres.
        max_length=40,
        choices=Status.choices,
        default=Status.PENDIENTE_VALIDACION,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Última edición hecha por el autor. Se diferencia de ``updated_at`` (que se
    # mueve con cualquier guardado, incluido un cambio de estado municipal) para
    # poder mostrar "editado el ..." solo cuando el ciudadano tocó el contenido.
    edited_at = models.DateTimeField(null=True, blank=True)
    # Cuándo se archivó, sea por decisión del municipio o por inactividad
    # (US-031). Va como campo y no se deduce del historial porque el listado de
    # "mis reportes" lo muestra y ese listado no trae el historial: deducirlo
    # ahí costaría una consulta por fila.
    archived_at = models.DateTimeField(null=True, blank=True)
    # Cuándo se le avisó al autor que su reporte estaba por archivarse. Existe
    # para que la verificación periódica sea idempotente: sin esto, cada corrida
    # dentro de la ventana de aviso mandaría la notificación de nuevo.
    archival_warning_sent_at = models.DateTimeField(null=True, blank=True)
    # Cuándo el operario registró la resolución (US-046). Es el instante desde
    # el que corre la ventana de objeción de US-047 y, además, **la fecha que
    # toma el indicador de tiempo de resolución**: los días de espera son un
    # mecanismo de control, no tiempo de trabajo municipal, y cargarlos al
    # indicador distorsionaría la gestión del municipio.
    closed_at = models.DateTimeField(null=True, blank=True)
    # Cuándo se le avisó al autor que el plazo de objeción estaba por vencer.
    # Mismo rol que ``archival_warning_sent_at``: vuelve idempotente la corrida.
    objection_warning_sent_at = models.DateTimeField(null=True, blank=True)
    # Cuántas veces el autor apeló un cierre (US-048). Se persiste sobre el
    # reporte porque el tope —una— lo verifica la máquina de estados antes de
    # ejecutar la transición, y ahí no hay más contexto que el reporte.
    appeal_count = models.PositiveSmallIntegerField(default=0)

    # El autor solo puede modificar o borrar su reporte mientras nadie más lo
    # miró: es decir, hasta que un validador lo confirma en terreno.
    #
    # ``REPORTADO`` salió de esta lista a propósito. Un reporte validado ya pasó
    # por el trabajo de otra persona y entró en la cola del municipio: dejar que
    # el autor le cambie la categoría o la dirección después de eso invalida esa
    # validación sin que nadie se entere.
    EDITABLE_STATUSES = frozenset({Status.PENDIENTE_VALIDACION})

    # Estados que dejan de listarse en el feed y en el mapa: el reporte ya no es
    # un problema activo (US-013). El autor los sigue viendo en "mis reportes" y
    # en el detalle, que es a donde lo lleva la notificación del cambio.
    INACTIVE_PUBLIC_STATUSES = frozenset({Status.CANCELADO, Status.ARCHIVADO})

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["municipality", "number"],
                name="unique_report_number_per_municipality",
            ),
            # US-042: o la foto está vacía, o ya pasó por el difuminado. No
            # hay un tercer caso. Va en la base y no solo en `save` porque
            # `update()` y `bulk_update()` no pasan por `save`: es lo que hace
            # del escenario 6 una afirmación y no una promesa.
            models.CheckConstraint(
                condition=models.Q(photo="")
                | models.Q(photo_status=PhotoStatus.PROCESADA),
                name="report_photo_only_when_processed",
            ),
        ]
        indexes = [
            # Búsqueda de duplicados (US-026): las igualdades primero y la
            # latitud después, así la caja de ``find_duplicate`` se resuelve
            # dentro del índice. Es parcial porque los cerrados, que con el
            # tiempo son la mayoría, nunca bloquean. Los estados repiten
            # ``duplicates.ACTIVE_STATUSES``, que no se puede importar acá.
            models.Index(
                fields=["municipality", "category", "latitude", "longitude"],
                name="report_duplicate_lookup",
                condition=models.Q(
                    status__in=[
                        "pendiente_validacion",
                        "reportado",
                        "en_proceso",
                        "resuelto_pendiente_confirmacion",
                    ],
                ),
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
        # Uno retirado por protección de datos no se edita: una foto nueva no lo
        # vuelve a publicar, así que ofrecerlo sería una promesa falsa.
        return self.status in self.EDITABLE_STATUSES and not self.is_withdrawn

    @property
    def is_withdrawn(self) -> bool:
        """Si se retiró por exponer un dato personal en su foto (US-043)."""
        return self.photo_removed_at is not None

    @property
    def is_on_privacy_hold(self) -> bool:
        """Si está retenido por protección de datos (US-043).

        Usa la anotación ``privacy_hold`` si el queryset la trae —la trae el
        feed, para no consultar por fila— y si no, consulta con la misma
        condición de ``on_privacy_hold()``.
        """
        annotated = getattr(self, "privacy_hold", None)
        if annotated is not None:
            return annotated
        return Report.objects.filter(pk=self.pk).filter(on_privacy_hold()).exists()

    def confirmation_count(self) -> int:
        """Me gusta que **cuentan como confirmación** de que el problema existe.

        No es el contador público de US-008 y no debe confundirse con él: el
        público cuenta todo, este descuenta a quien no puede confirmar nada.

        Quedan afuera dos grupos, y por motivos distintos:

        - **El autor.** Ya afirmó que el problema existe al reportarlo; contar
          su propio me gusta sería contar dos veces la misma afirmación.
        - **Las cuentas de trabajo.** La confirmación municipal se ejecuta por
          la vía de US-036 —yendo al lugar—, no por interacción social. Un
          validador que da me gusta está participando del feed, no validando.

        Vive acá y no en la vista que evalúa el umbral porque el filtro tiene que
        ser uno solo: repetido en dos lugares, uno de los dos se olvidaría de
        excluir a alguien y el umbral se alcanzaría antes de lo debido.
        """
        # Import local: ``users`` importa ``reports`` a través del modelo, así
        # que a nivel de módulo esto sería una dependencia circular.
        from urbancheck.users.models import User  # noqa: PLC0415

        return (
            self.likes.exclude(user_id=self.author_id)
            .exclude(user__role__in=list(User.WORK_ROLES))
            .count()
        )


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
    status = models.CharField(max_length=40, choices=Report.Status.choices)
    previous_status = models.CharField(
        max_length=40,
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
    # De dónde salió la transición, más allá de a qué estado llegó. Dos caminos
    # pueden producir el mismo estado y certificar cosas distintas —un validador
    # que fue al lugar y diez vecinos que confirmaron dejan los dos el reporte
    # en *Reportado*—, y el panel necesita distinguirlos (US-038).
    #
    # Lo escribe ``apply_transition`` desde la tabla de transiciones: quien
    # invoca no lo elige, así que ninguna operación puede quedar asentada con un
    # origen que no le corresponde.
    origin = models.CharField(max_length=30, blank=True, default="")
    # Cuántas confirmaciones tenía el reporte al validarse colectivamente
    # (US-040, escenario 9). Nulo en toda otra transición: es un dato de esa
    # sola, y guardarlo evita que el panel lo recalcule sobre un conteo que para
    # entonces ya cambió.
    confirmation_count = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.report_id}: {self.previous_status or '—'} → {self.status}"


class ReportAreaAssignment(models.Model):
    """Traza de cada asignación de un reporte a un área operativa (US-028).

    ``ReportStatusHistory`` no alcanza: la reasignación de un reporte que ya
    está *En proceso* no cambia el estado, así que no dejaría ningún asiento y
    el historial mostraría un área nueva sin decir quién la puso ni cuándo.

    Se escribe en la misma transacción que la asignación, igual que el historial
    de estados: no puede quedar un reporte con un área nueva y sin registro.
    """

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="area_assignments",
    )
    # Nulo en la asignación inicial, que es la única sin área anterior.
    previous_area = models.ForeignKey(
        "municipalities.OperationalArea",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments_from",
    )
    area = models.ForeignKey(
        "municipalities.OperationalArea",
        on_delete=models.PROTECT,
        related_name="assignments_to",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        previous = self.previous_area or "—"
        return f"{self.report_id}: {previous} → {self.area}"


class ResolutionEvidence(PendingPhotoMixin, models.Model):
    """El parte de trabajo del operario que cerró el reporte (US-046).

    Es una entidad propia y no un puñado de campos sobre el reporte, por dos
    razones: un reporte reabierto por apelación acumula **más de una** —el
    segundo cierre no pisa al primero, los dos quedan para poder compararlos
    (US-048, escenario 9)— y la evidencia sobrevive a la reapertura.

    No hay que confundirla con la respuesta oficial de US-024: aquella es la voz
    de la institución y compromete al municipio; esta describe qué se hizo
    físicamente, en el lugar y en el momento.

    **La identidad del operario no se muestra al ciudadano.** Ante el vecino
    responde el área operativa; quién fue se ve únicamente en el panel, con el
    mismo criterio de protección del personal de US-038.
    """

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="resolution_evidences",
    )
    # Vacía solo si se retiró por protección de datos (US-043, escenario 11): el
    # parte de trabajo conserva la descripción y el estado del reporte no se
    # toca.
    photo = models.ImageField(upload_to="resolutions/%Y/%m/", blank=True)
    photo_removed_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField()
    # Quién cerró. ``SET_NULL`` porque la cuenta puede desaparecer y el parte de
    # trabajo tiene que sobrevivirle.
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolution_evidences",
    )
    # El área **al momento del cierre**, no la que el operario tenga hoy: un
    # traslado posterior no puede reescribir quién se hizo cargo de este trabajo
    # (US-044, escenario 5).
    operational_area = models.ForeignKey(
        "municipalities.OperationalArea",
        on_delete=models.PROTECT,
        related_name="resolution_evidences",
    )
    # Desde dónde se registró. Se guarda para poder auditar después la
    # verificación de proximidad que ya se hizo al cerrar.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Cronológico ascendente: el hilo se lee del primer cierre al último.
        ordering = ["created_at"]
        constraints = [
            # US-042: o la foto está vacía, o ya pasó por el difuminado. No
            # hay un tercer caso. Va en la base y no solo en `save` porque
            # `update()` y `bulk_update()` no pasan por `save`: es lo que hace
            # del escenario 6 una afirmación y no una promesa.
            models.CheckConstraint(
                condition=models.Q(photo="")
                | models.Q(photo_status=PhotoStatus.PROCESADA),
                name="evidence_photo_only_when_processed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_id}: cierre de {self.operational_area}"


class ResolutionComparison(models.Model):
    """La comparación automática entre el antes y el después de un cierre (US-015).

    Se cuelga de la **evidencia**, no del reporte: un segundo cierre tras una
    apelación trae su propia comparación y la del primero se conserva
    (escenario 7).

    **Es informativa y no decide nada.** No hay ninguna FK ni escritura hacia el
    reporte: el veredicto no cambia el estado, no toca el plazo de US-047 y no
    habilita ni impide transiciones. El control efectivo sobre un cierre mal
    hecho es la apelación del vecino (US-048), que tiene a alguien que responde
    por ella; un modelo que se equivoca lo hace en silencio.

    Solo la ve el panel municipal (escenario 8): es control interno, no una
    calificación pública del trabajo del operario.
    """

    class Status(models.TextChoices):
        PENDING = "pendiente", "Comparación en curso"
        COMPLETED = "completada", "Completada"
        # Fallo del servicio, reintentos agotados, respuesta fuera de esquema o
        # servicio sin configurar. Para el panel es lo mismo: no hay veredicto.
        UNAVAILABLE = "no_disponible", "Comparación no disponible"
        # Falta alguna de las dos imágenes (escenario 6).
        NO_MATERIAL = "sin_material", "Sin material suficiente para comparar"

    class Verdict(models.TextChoices):
        CONSISTENT = "consistente", "Resolución consistente"
        # Los tres motivos de un cierre dudoso del escenario 3. Se guardan por
        # separado porque "a revisar" no dice qué mirar, y esto sí.
        PROBLEM_PERSISTS = "problema_persistente", "El problema sigue presente"
        DIFFERENT_PLACE = "lugar_distinto", "Las imágenes no son del mismo lugar"
        INCONSISTENT_WORK = (
            "trabajo_incoherente",
            "El cambio no coincide con lo declarado",
        )

    evidence = models.OneToOneField(
        ResolutionEvidence,
        on_delete=models.CASCADE,
        related_name="comparison",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    verdict = models.CharField(
        max_length=20,
        choices=Verdict.choices,
        blank=True,
        default="",
    )
    # La explicación breve devuelta por el modelo, tal cual.
    explanation = models.TextField(blank=True, default="")
    # Qué modelo respondió, para poder auditar el comportamiento (escenario 9).
    model_name = models.CharField(max_length=100, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    # Un código corto, nunca el cuerpo de la respuesta ni rutas de archivos: la
    # regla de US-041 sobre logs y trazas vale también acá.
    failure_reason = models.CharField(max_length=50, blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["requested_at"]

    def __str__(self) -> str:
        return f"{self.evidence_id}: {self.status} {self.verdict}".strip()

    @property
    def is_doubtful(self) -> bool:
        """Si el cierre merece revisión: hay veredicto y no es consistente."""
        return bool(self.verdict) and self.verdict != self.Verdict.CONSISTENT


class ResolutionAppeal(PendingPhotoMixin, models.Model):
    """La objeción del autor a un cierre que no resolvió el problema (US-048).

    Es el control humano sobre el cierre: el operario certifica su propio
    trabajo, y esto es lo que impide que esa certificación sea la única palabra.

    Se conserva junto con la evidencia que objeta —no la reemplaza— para que el
    operario y el agente puedan comparar el antes y el después.
    """

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="resolution_appeals",
    )
    # La evidencia objetada. Nula solo si el cierre se borró, cosa que hoy no
    # ocurre por ninguna vía.
    evidence = models.ForeignKey(
        ResolutionEvidence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeals",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resolution_appeals",
    )
    reason = models.TextField()
    # Obligatoria al apelar —lo exige el serializer—, pero el campo admite
    # vacío: con la publicación diferida (US-042) la apelación nace sin foto y
    # la recibe recién cuando la tarea termina de difuminarla.
    photo = models.ImageField(upload_to="appeals/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            # US-042: o la foto está vacía, o ya pasó por el difuminado. No
            # hay un tercer caso. Va en la base y no solo en `save` porque
            # `update()` y `bulk_update()` no pasan por `save`: es lo que hace
            # del escenario 6 una afirmación y no una promesa.
            models.CheckConstraint(
                condition=models.Q(photo="")
                | models.Q(photo_status=PhotoStatus.PROCESADA),
                name="appeal_photo_only_when_processed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_id}: apelación de {self.author}"


class OfficialResponse(models.Model):
    """Comunicación institucional del municipio sobre un reporte (US-024).

    Es un **hilo inmutable**, no un campo editable: el reporte acumula
    respuestas sucesivas en orden cronológico y ninguna se edita ni se elimina
    una vez publicada. Permitir que el municipio reescriba lo que dijo
    públicamente contradice el principio de transparencia que sostiene el
    producto —si se publica un compromiso de plazo y después se lo reemplaza, el
    ciudadano pierde la evidencia del original—. Una corrección se publica como
    una respuesta nueva.

    La inmutabilidad se garantiza por la **ausencia** de endpoints de
    actualización y de borrado, no por una validación que después alguien puede
    relajar.

    No hay que confundirla con la evidencia de resolución del operario (US-046):
    esta es la voz de la institución y compromete al municipio; aquella es un
    parte de trabajo que describe qué se hizo en el lugar.
    """

    #: Tope de una respuesta oficial. Es una comunicación institucional, no un
    #: expediente: si no entra acá, lo que corresponde es publicar otra.
    MAX_LENGTH = 2000

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="official_responses",
    )
    # Quién la publicó. Su identidad se muestra únicamente en el panel: ante el
    # ciudadano responde la municipalidad, con el mismo criterio de protección
    # del personal de US-038.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="official_responses",
    )
    # Se deriva del reporte al publicar y se guarda: es el emisor de cara al
    # ciudadano, y tiene que sobrevivir aunque la cuenta del agente desaparezca.
    municipality = models.ForeignKey(
        "municipalities.Municipality",
        on_delete=models.PROTECT,
        related_name="official_responses",
    )
    text = models.TextField(max_length=MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Cronológico y ascendente: el hilo se lee de la primera comunicación a
        # la última, que es el orden en que ocurrió la gestión.
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.report_id}: respuesta oficial de {self.municipality}"


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
    # Cuándo se dio. Lo necesita el archivado por inactividad de US-031, que
    # mide "sin likes ni comentarios" contra la interacción más reciente. Los
    # likes anteriores a este campo quedan fechados en la migración con la
    # creación de su reporte, que es la única fecha que se sabe cierta.
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "user"], name="unique_report_like")
        ]


COMPLAINT_COMMENT_MAX_LENGTH = 500


def _reasons_for(catalog: dict, recipient: str) -> frozenset:
    """Los motivos del catálogo de denuncias que resuelve ``recipient``."""
    return frozenset(reason for reason, to in catalog.items() if to == recipient)


class ReportComplaintQuerySet(models.QuerySet):
    """Quién resuelve cada denuncia se decide por su motivo, en un solo lugar."""

    def for_platform_review(self) -> ReportComplaintQuerySet:
        """Las que resuelve el administrador de la plataforma (US-043).

        No pasan por la capa de jurisdicción: la protección de datos es una
        obligación de la plataforma, no del municipio, y el administrador ve
        las de todas las municipalidades.
        """
        return self.filter(reason__in=ReportComplaint.PLATFORM_REASONS)

    def for_municipal_review(self) -> ReportComplaintQuerySet:
        """Las que resuelve el agente de la jurisdicción (US-021, US-049).

        La bandeja municipal de US-049 tiene que partir de acá para nacer sin
        las solicitudes por dato personal (US-043, escenario 10): si la bandeja
        filtrara por su cuenta, el día que se sume un motivo de plataforma
        nuevo se filtraría hacia el municipio.
        """
        return self.exclude(reason__in=ReportComplaint.PLATFORM_REASONS)


class ReportComplaint(models.Model):
    """Una denuncia de un usuario sobre un reporte publicado.

    Es la entidad del botón *Denunciar* de US-021. US-043 la inauguró con un
    solo motivo —el dato personal que el difuminado no detectó— y US-021 le
    sumó los suyos: lo que cambia entre motivos es **quién resuelve y con qué
    efecto**, no la entidad, y por eso es un modelo con un catálogo y no uno
    por motivo.

    Una denuncia por dato personal apunta a una imagen concreta: la del
    reporte, o la de un parte de trabajo del operario cuando
    ``resolution_evidence`` está cargado (US-043, escenario 11). En los dos
    casos oculta el reporte entero, porque es el reporte lo que se publica. Las
    de contenido (US-021) apuntan al reporte y no a un archivo: ``image_name``
    queda vacío y no ocultan nada.

    Es también el registro de cumplimiento de la RN-12: recepción, resolución,
    decisión y responsable quedan en la fila y no se borran.
    """

    class Reason(models.TextChoices):
        CONTENIDO_INAPROPIADO = (
            "contenido_inapropiado",
            "Contenido inapropiado u ofensivo",
        )
        REPORTE_FALSO = "reporte_falso", "Reporte falso o inexistente"
        DATO_PERSONAL = "dato_personal", "Dato personal visible"

    class Recipient(models.TextChoices):
        """Quién resuelve una denuncia. No existe el rol moderador (US-021)."""

        AGENTE_MUNICIPAL = "agente_municipal", "Agente municipal"
        ADMIN_PLATAFORMA = "admin_plataforma", "Administrador de la plataforma"

    class Status(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        IMAGEN_ELIMINADA = "imagen_eliminada", "Imagen eliminada"
        DESESTIMADA = "desestimada", "Desestimada"

    #: **El catálogo de motivos**: cada uno con su destinatario (US-021,
    #: escenario 3). El enrutamiento se deriva de acá —``PLATFORM_REASONS``,
    #: los dos querysets de revisión, el acuse que recibe el vecino— y no de
    #: condicionales en las vistas. Un motivo nuevo se suma en esta tabla; un
    #: test verifica que ninguno quede sin destinatario.
    REASON_RECIPIENTS = {
        Reason.CONTENIDO_INAPROPIADO: Recipient.AGENTE_MUNICIPAL,
        Reason.REPORTE_FALSO: Recipient.AGENTE_MUNICIPAL,
        Reason.DATO_PERSONAL: Recipient.ADMIN_PLATAFORMA,
    }
    #: Motivos que resuelve el administrador de la plataforma y no el municipio.
    PLATFORM_REASONS = _reasons_for(REASON_RECIPIENTS, Recipient.ADMIN_PLATAFORMA)
    #: Motivos que ocultan el reporte mientras están pendientes. Es la única
    #: excepción al principio de que una denuncia no altera la visibilidad.
    HIDING_REASONS = frozenset({Reason.DATO_PERSONAL})

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="complaints",
    )
    # Nulo cuando lo denunciado es la foto del reporte.
    resolution_evidence = models.ForeignKey(
        ResolutionEvidence,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="complaints",
    )
    # El archivo denunciado **tal como se llamaba al recibir la solicitud**. Es
    # la referencia a la imagen del escenario 1, y también lo que se borra: si
    # el autor reemplaza la foto mientras la solicitud espera, lo que expone el
    # dato personal es el archivo denunciado, no el nuevo.
    # Vacío en las denuncias de contenido (US-021), que no señalan un archivo.
    image_name = models.CharField(max_length=255, blank=True)
    # ``SET_NULL``: si la cuenta desaparece, el registro de cumplimiento no.
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="complaints",
    )
    reason = models.CharField(max_length=30, choices=Reason.choices)
    # Opcional (US-021, escenario 1). Lo lee quien resuelve y nadie más.
    comment = models.TextField(blank=True, max_length=COMPLAINT_COMMENT_MAX_LENGTH)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDIENTE,
    )
    # Fecha de recepción: el plazo de la RN-12 corre desde acá y desde ningún
    # otro campo. Por eso no hay ``updated_at`` en el modelo.
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_complaints",
    )

    objects = ReportComplaintQuerySet.as_manager()

    class Meta:
        # La más vieja primero: es la que está más cerca de vencer.
        ordering = ["created_at"]
        constraints = [
            # Una sola solicitud en curso por persona, imagen y motivo (US-043,
            # escenario 9). ``nulls_distinct=False`` porque la foto del reporte
            # se identifica con ``resolution_evidence`` nulo, y con la semántica
            # por defecto de SQL dos nulos nunca chocan.
            models.UniqueConstraint(
                fields=["reporter", "report", "resolution_evidence", "reason"],
                condition=models.Q(status="pendiente"),
                nulls_distinct=False,
                name="unique_pending_complaint_per_image",
            ),
            # Una sola denuncia de contenido por persona, reporte y motivo, para
            # siempre y no solo mientras está pendiente (US-021, escenario 6):
            # que el municipio la desestime no habilita a presentarla de nuevo.
            # Las de dato personal quedan fuera porque se cuentan por imagen
            # —la restricción de arriba— y sí se pueden repetir tras una
            # decisión, si la foto cambió.
            models.UniqueConstraint(
                fields=["reporter", "report", "reason"],
                condition=~models.Q(reason="dato_personal"),
                name="unique_content_complaint_per_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_id}: {self.reason} ({self.status})"

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDIENTE

    @property
    def recipient(self) -> str:
        """A quién va dirigida, según el catálogo."""
        return self.REASON_RECIPIENTS[self.reason]
