from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from urbancheck.reports.geo import MIN_BOUNDARY_POINTS
from urbancheck.reports.geo import point_in_polygon


class MunicipalityQuerySet(models.QuerySet):
    def active(self) -> MunicipalityQuerySet:
        """Municipalidades vigentes: excluye las dadas de baja."""
        return self.filter(is_active=True)


class Municipality(models.Model):
    """Municipio dado de alta en la plataforma (US-017).

    Es la unidad de jurisdicción: usuarios municipales y reportes cuelgan de
    acá, y la restricción de acceso de US-034 se apoya en este vínculo.

    Cada municipio declara un **área de cobertura**: el polígono de su límite,
    trazado sobre el mapa. Un reporte nuevo se asocia al municipio que lo
    contiene, de modo que la localidad de Córdoba no recibe los reportes de
    Villa María.

    Antes esto era un círculo —centro y radio—, y no alcanzaba. Dos ciudades
    pegadas como Villa María y Villa Nueva están separadas por un río: cualquier
    círculo lo bastante grande para cubrir una entera se come parte de la otra,
    porque un círculo no puede saber que hay un límite en el medio. El polígono
    sí sigue ese límite.
    """

    city = models.CharField(_("city"), max_length=120)
    province = models.CharField(_("province"), max_length=120)

    # Centro geográfico de la ciudad, tomado del centroide oficial de Georef.
    # Ya no delimita nada —de eso se encarga ``boundary``—: es dónde se abre el
    # mapa al editar el municipio y al mirar sus reportes.
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    boundary = models.JSONField(
        _("coverage boundary"),
        null=True,
        blank=True,
        help_text=_(
            "Polígono del límite del municipio, como lista de pares "
            "[latitud, longitud]. Los reportes que caen adentro le llegan.",
        ),
    )

    # Baja lógica: un municipio con reportes o usuarios no se puede borrar de la
    # base sin perder historia, así que se lo desactiva. Deja de recibir
    # reportes nuevos y de aparecer en los listados.
    is_active = models.BooleanField(_("active"), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MunicipalityQuerySet.as_manager()

    class Meta:
        verbose_name = _("municipality")
        verbose_name_plural = _("municipalities")
        ordering = ["city", "province"]
        constraints = [
            models.UniqueConstraint(
                fields=["city", "province"],
                name="unique_municipality_city_province",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.city} ({self.province})"

    @property
    def has_coverage(self) -> bool:
        """Si tiene un área trazada contra la cual evaluar reportes.

        Un municipio sin área no recibe reportes nuevos: es preferible eso a
        adivinar un límite y quedarse con reclamos que no le corresponden.
        """
        return (
            isinstance(self.boundary, list)
            and len(self.boundary) >= MIN_BOUNDARY_POINTS
        )

    def contains(self, latitude: float, longitude: float) -> bool:
        """Si el punto cae dentro del área de cobertura del municipio."""
        if not self.has_coverage:
            return False
        return point_in_polygon(float(latitude), float(longitude), self.boundary)


#: Caracteres aceptados en un teléfono de contacto: dígitos y los separadores
#: con los que se escribe un número acá —espacios, guiones, paréntesis y el
#: prefijo internacional—. No se normaliza el formato: se guarda como lo
#: escribió el agente, que es como lo va a leer quien tenga que llamar.
PHONE_REGEX = r"^\+?[0-9][0-9\s\-()]{5,29}$"

PHONE_INVALID_MESSAGE = (
    "El teléfono solo puede tener números, espacios, guiones, paréntesis y "
    "un prefijo «+» inicial."
)

AREA_NAME_TAKEN_MESSAGE = "Ya existe un área operativa con ese nombre en tu municipalidad."


class OperationalAreaQuerySet(models.QuerySet):
    """Consultas de áreas operativas acotadas por jurisdicción (US-034).

    Mismo contrato que ``Report.objects.for_user`` y ``User.objects.for_user``:
    el filtro por municipalidad se declara una vez por modelo y las vistas lo
    consumen a través de ``JurisdictionScopedMixin``.
    """

    def for_user(self, user) -> OperationalAreaQuerySet:
        """Áreas de la municipalidad de ``user``.

        Default seguro idéntico al del resto: sin municipalidad, ninguna área.
        """
        municipality_id = getattr(user, "municipality_id", None)
        if not municipality_id:
            return self.none()
        return self.filter(municipality_id=municipality_id)

    def active(self) -> OperationalAreaQuerySet:
        """Las que se ofrecen para asignar un reporte (US-028)."""
        return self.filter(is_active=True)

    def with_report_count(self) -> OperationalAreaQuerySet:
        """Anota cuántos reportes tiene vinculados cada área.

        Es la cifra que el listado de gestión muestra por fila y la que hace
        explícita la consecuencia de desactivar un área. Va como anotación y no
        como consulta por fila para no producir un N+1 en la tabla del panel.
        """
        return self.annotate(report_count=models.Count("reports", distinct=True))


class OperationalArea(models.Model):
    """Dependencia municipal que resuelve reportes en la vía pública (US-039).

    Es la unidad de distribución interna del trabajo: el agente asigna cada
    reporte validado a un área (US-028) y los operarios de esa área lo ven en
    su bandeja (US-045).

    **No se borra, se desactiva.** Un área con reportes asignados no se puede
    eliminar sin perder la trazabilidad de quién se hizo cargo de cada reclamo,
    así que la baja es lógica: deja de ofrecerse para asignar reportes nuevos y
    conserva el vínculo con los que ya tenía.

    Se registra **un único teléfono** por área. Si la dependencia tiene varios
    números, se carga el de contacto principal: la relación 1-N de contactos
    queda fuera del alcance del proyecto.
    """

    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.PROTECT,
        related_name="operational_areas",
        verbose_name=_("municipality"),
    )
    name = models.CharField(_("name"), max_length=120)
    contact_email = models.EmailField(_("contact email"))
    contact_phone = models.CharField(
        _("contact phone"),
        max_length=30,
        validators=[RegexValidator(regex=PHONE_REGEX, message=PHONE_INVALID_MESSAGE)],
    )
    is_active = models.BooleanField(_("active"), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OperationalAreaQuerySet.as_manager()

    class Meta:
        verbose_name = _("operational area")
        verbose_name_plural = _("operational areas")
        ordering = ["name"]
        constraints = [
            # Compuesta sobre municipalidad y nombre, no sobre el nombre solo:
            # "Obras Públicas" existe en todos los municipios del país, y dos
            # municipalidades distintas tienen que poder registrarla.
            #
            # Sobre ``Lower(name)`` para que "Obras Públicas" y "obras
            # públicas" sean la misma área: quien la carga por segunda vez está
            # duplicando la dependencia, no creando otra.
            models.UniqueConstraint(
                Lower("name"),
                "municipality",
                name="unique_operational_area_name_per_municipality",
                violation_error_message=AREA_NAME_TAKEN_MESSAGE,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.municipality})"
