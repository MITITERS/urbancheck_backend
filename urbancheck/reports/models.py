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
    photo = models.ImageField(upload_to="reports/%Y/%m/")
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


class ResolutionEvidence(models.Model):
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
    photo = models.ImageField(upload_to="resolutions/%Y/%m/")
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

    def __str__(self) -> str:
        return f"{self.report_id}: cierre de {self.operational_area}"


class ResolutionAppeal(models.Model):
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
    # Obligatoria: una apelación sin evidencia no se distingue de una objeción
    # caprichosa y no reabre trabajo municipal.
    photo = models.ImageField(upload_to="appeals/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

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
