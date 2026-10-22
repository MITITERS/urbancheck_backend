from __future__ import annotations

import uuid

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
        return self.filter(publicly_visible_condition())

    def publishable(self) -> ReportQuerySet:
        """``publicly_visible`` sin la condición de estado.

        Para las superficies que se acotan por estado por su cuenta —la bandeja
        de validación lista solo pendientes, pero valida y rechaza por id—: la
        imagen tiene que estar difuminada y fuera de toda revisión por dato
        personal, igual que para el feed.
        """
        return self.filter(publishable_condition())

    def visible_to(self, user) -> ReportQuerySet:
        """Lo que ``user`` puede abrir por id: el detalle y lo que cuelga de él.

        Para un tercero son las mismas condiciones que ``publicly_visible``
        (Sprint 5, punto 6.1). El autor ve siempre el suyo: su reclamo
        cancelado o archivado —ahí lo lleva el aviso del cambio de estado, que
        solo le llega a él—, marcado como en revisión o retirado por protección
        de datos, o con la imagen todavía en procesamiento (US-042). Ocultarle
        su propio reporte no protege a nadie.

        Hasta el Sprint 5 los estados inactivos se abrían por id para
        cualquiera; el punto 6.1 los cierra también para terceros.
        """
        return self.filter(
            models.Q(author_id=user.pk) | publicly_visible_condition(),
        )

    def moderation_notices(self) -> ReportQuerySet:
        """Reportes descartados por moderación municipal, vigente el descarte.

        No son visibles: salen del feed y del mapa por su estado, como
        cualquier cancelado. Pero el motivo del descarte es público (US-049,
        escenario 5) —es el contrapeso de que el municipio pueda ocultar
        reclamos—, así que el detalle se puede abrir por id para leerlo, y
        **solo** eso: el serializer reducido no lleva foto, descripción ni
        denunciantes. Nada que cuelgue del detalle —comentarios, me gusta,
        denuncias— se habilita por acá: esas vistas siguen en ``visible_to``.
        """
        return self.filter(
            status=Report.Status.CANCELADO,
        ).filter(
            models.Exists(
                ModerationDecision.objects.filter(
                    report=models.OuterRef("pk"),
                    outcome=ModerationDecision.Outcome.DESCARTADO,
                    reverted_at__isnull=True,
                ),
            ),
        )


def publishable_condition() -> models.Q:
    """La imagen se puede mostrar: difuminada, sin revisión en curso, no retirada.

    Junto con ``publicly_visible_condition`` es la **única** definición de la
    visibilidad pública (Sprint 5, punto 6.1). Todo lo demás la reutiliza.
    """
    return (
        ~models.Q(on_privacy_hold())
        & models.Q(photo_removed_at__isnull=True)
        & photo_ready()
    )


def publicly_visible_condition() -> models.Q:
    """Las tres condiciones del punto 6.1 sobre un reporte, para un tercero.

    1. su estado es visible (no Cancelado ni Archivado);
    2. su imagen está procesada —o se retiró por protección de datos, que en
       este producto retira el reporte entero (US-043, decisión del equipo)—;
    3. no tiene una solicitud por dato personal en curso.
    """
    active = ~models.Q(status__in=Report.INACTIVE_PUBLIC_STATUSES)
    return active & publishable_condition()


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
    # El identificador del enlace para compartir (US-030). Aleatorio y no el id:
    # el id es correlativo, y con él cualquiera podría recorrer los reportes
    # cambiando un número en la URL.
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
    )
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
            # Estadísticas del panel (US-023): todo filtra por municipio y por
            # fecha de creación dentro del período.
            models.Index(
                fields=["municipality", "created_at"],
                name="report_muni_created",
            ),
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

    def active_discard(self) -> ModerationDecision | None:
        """El descarte por moderación vigente, si lo hay (US-049).

        Es el que hay que revertir y el que el vecino puede apelar. Uno
        revertido ya no cuenta: si el agente vuelve a descartar el reporte
        restituido, es una decisión nueva con su propia apelación.
        """
        return (
            self.moderation_decisions.filter(
                outcome=ModerationDecision.Outcome.DESCARTADO,
                reverted_at__isnull=True,
            )
            .order_by("-created_at", "-pk")
            .first()
        )

    @property
    def closure_appeals(self) -> list[ResolutionAppeal]:
        """Las objeciones a un cierre (US-048), sin las apelaciones de moderación.

        Las dos comparten modelo (US-049 lo reutiliza con un tipo), pero solo
        las de cierre forman parte del hilo de resolución que muestran el panel
        y la app. Se filtra en Python sobre ``resolution_appeals.all()`` para
        aprovechar el ``prefetch_related`` que ya traen las vistas.
        """
        return [
            appeal
            for appeal in self.resolution_appeals.all()
            if appeal.kind == ResolutionAppeal.Kind.CIERRE
        ]

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
    # Con qué rol actuó ``changed_by``, tal como era en ese momento (C-15). El
    # administrador de la plataforma ejecuta las acciones del panel con las
    # reglas del agente municipal: sin esto, el asiento no distingue quién de
    # los dos lo hizo una vez que la cuenta cambia de rol o se borra. Vacío en
    # los asientos anteriores a C-15 y en los automáticos, sin usuario.
    changed_by_role = models.CharField(max_length=30, blank=True, default="")
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
        indexes = [
            # Indicadores de US-050: cada uno busca, por reporte, la primera o
            # la última vez que pasó por un estado.
            models.Index(
                fields=["report", "status", "created_at"],
                name="history_report_status_at",
            ),
        ]

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
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
    )
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
    """La apelación del autor a una decisión sobre su reporte.

    Dos tipos, un solo mecanismo (US-049 pide no crear un segundo):

    - **De cierre** (US-048): la objeción a un cierre que no resolvió el
      problema. Es el control humano sobre el cierre: el operario certifica su
      propio trabajo, y esto es lo que impide que esa certificación sea la
      única palabra. Se conserva junto con la evidencia que objeta para que el
      operario y el agente puedan comparar el antes y el después. Reabre el
      reporte en el acto; no hay nadie que la "resuelva".
    - **De moderación** (US-049): contra el descarte por moderación municipal.
      No cambia el estado —el reporte sigue Cancelado mientras se revisa— y la
      resuelve el administrador de la plataforma, nunca el municipio que
      descartó. Va sin foto. Una sola por descarte.
    """

    class Kind(models.TextChoices):
        CIERRE = "cierre", "Objeción del cierre"
        MODERACION = "moderacion", "Apelación de moderación"

    class Status(models.TextChoices):
        """Solo para las de moderación. Las de cierre no se resuelven: reabren."""

        PENDIENTE = "pendiente", "Pendiente"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"

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
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CIERRE)
    # El descarte apelado. Solo en las de moderación.
    moderation_decision = models.ForeignKey(
        "ModerationDecision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appeals",
    )
    status = models.CharField(max_length=20, choices=Status.choices, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_appeals",
    )
    # Por qué el administrador hizo lugar o no. Le llega al autor.
    resolution_reason = models.TextField(blank=True)
    reason = models.TextField()
    # Obligatoria al apelar una objeción de cierre —lo exige el serializer—;
    # la de moderación no lleva. El campo admite
    # vacío: con la publicación diferida (US-042) la apelación nace sin foto y
    # la recibe recién cuando la tarea termina de difuminarla.
    photo = models.ImageField(upload_to="appeals/%Y/%m/", blank=True)
    # Retirada por protección de datos (US-043, escenario 1): la apelación y su
    # motivo quedan; la foto no.
    photo_removed_at = models.DateTimeField(null=True, blank=True)
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
            # Una sola apelación por descarte (US-049, escenario 7): si el
            # administrador la rechaza, el reporte queda Cancelado y no admite
            # otra. Si la acepta, un descarte nuevo es otra decisión.
            models.UniqueConstraint(
                fields=["moderation_decision"],
                condition=models.Q(kind="moderacion"),
                name="one_appeal_per_moderation_decision",
            ),
            # Las de moderación siempre apuntan a un descarte; las de cierre
            # nunca.
            models.CheckConstraint(
                condition=(
                    models.Q(kind="moderacion", moderation_decision__isnull=False)
                    | models.Q(kind="cierre", moderation_decision__isnull=True)
                ),
                name="appeal_kind_matches_decision",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.report_id}: apelación de {self.author} ({self.kind})"

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDIENTE


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
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Comentario {self.pk} en el reporte {self.report_id}"


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
            models.UniqueConstraint(
                fields=["report", "user"],
                name="unique_report_like",
            ),
        ]

    def __str__(self) -> str:
        return f"Me gusta de {self.user_id} en el reporte {self.report_id}"


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
    reporte, la de un parte de trabajo del operario cuando
    ``resolution_evidence`` está cargado (US-043, escenario 11), o la de una
    apelación del autor cuando lo está ``resolution_appeal`` (escenario 1).
    En todos los casos oculta el reporte entero, porque es el reporte lo que
    se publica. Las
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
        #: El agente le dio la razón al denunciante y descartó el reporte
        #: (US-049). ``desestimada`` cubre el caso contrario en los dos
        #: circuitos.
        REPORTE_DESCARTADO = "reporte_descartado", "Reporte descartado"

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
    # Nulo salvo cuando lo denunciado es la foto de una apelación (US-048).
    resolution_appeal = models.ForeignKey(
        ResolutionAppeal,
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
    # La decisión de moderación que la resolvió (US-049). Varias denuncias
    # sobre un mismo reporte se resuelven en **una** decisión (escenario 2).
    moderation_decision = models.ForeignKey(
        "ModerationDecision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="complaints",
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
                fields=[
                    "reporter",
                    "report",
                    "resolution_evidence",
                    "resolution_appeal",
                    "reason",
                ],
                condition=models.Q(status="pendiente"),
                nulls_distinct=False,
                name="unique_pending_complaint_per_image",
            ),
            # Una imagen por denuncia: la del reporte, la de un cierre o la de
            # una apelación, nunca dos a la vez.
            models.CheckConstraint(
                condition=models.Q(resolution_evidence__isnull=True)
                | models.Q(resolution_appeal__isnull=True),
                name="complaint_targets_one_image",
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
    def target(self):
        """El dueño de la imagen denunciada: cierre, apelación o el reporte."""
        return self.resolution_evidence or self.resolution_appeal or self.report

    @property
    def image_kind(self) -> str:
        if self.resolution_evidence_id is not None:
            return "resolution_evidence"
        if self.resolution_appeal_id is not None:
            return "resolution_appeal"
        return "report"

    @property
    def recipient(self) -> str:
        """A quién va dirigida, según el catálogo."""
        return self.REASON_RECIPIENTS[self.reason]


class ModerationDecision(models.Model):
    """Lo que decidió el agente municipal sobre las denuncias de un reporte (US-049).

    Una fila por decisión, no por denuncia: varias denuncias sobre un mismo
    reporte se resuelven juntas (escenario 2) y todas apuntan acá.

    La moderación de contenido es del agente municipal —no existe un rol
    moderador—, y darle al municipio la facultad de ocultar reclamos tiene
    contrapesos que viven en esta fila:

    - el ``reason`` es **público** en el detalle del reporte descartado;
    - ``previous_status`` permite que el administrador restituya el reporte al
      estado exacto que tenía, sin asumir que era Reportado;
    - ``reverted_at`` / ``reverted_by`` registran esa reversión, por apelación o
      de oficio.
    """

    class Outcome(models.TextChoices):
        DESCARTADO = "descartado", "Reporte descartado"
        DESESTIMADO = "desestimado", "Denuncias desestimadas"

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="moderation_decisions",
    )
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    reason = models.TextField()
    # El estado del reporte al descartarlo. Vacío al desestimar, que no lo
    # mueve.
    previous_status = models.CharField(max_length=40, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="moderation_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reverted_moderation_decisions",
    )
    revert_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.report_id}: {self.outcome}"

    @property
    def is_active_discard(self) -> bool:
        return self.outcome == self.Outcome.DESCARTADO and self.reverted_at is None
