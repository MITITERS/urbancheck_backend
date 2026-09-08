from __future__ import annotations

from django.db import models
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
