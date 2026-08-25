from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class MunicipalityQuerySet(models.QuerySet):
    def active(self) -> MunicipalityQuerySet:
        """Municipalidades vigentes: excluye las dadas de baja."""
        return self.filter(is_active=True)


class Municipality(models.Model):
    """Municipio dado de alta en la plataforma (US-017).

    Es la unidad de jurisdicción: usuarios municipales y reportes cuelgan de
    acá, y la restricción de acceso de US-034 se apoya en este vínculo.

    Cada municipio declara un **área de cobertura**: un centro geográfico y un
    radio en kilómetros. Un reporte nuevo se asocia al municipio que lo cubre,
    de modo que la localidad de Córdoba no recibe los reportes de Villa María.
    Es una aproximación circular deliberada: la resolución por polígono de
    límites reales sigue diferida a una iteración futura.
    """

    city = models.CharField(_("city"), max_length=120)
    province = models.CharField(_("province"), max_length=120)

    # Centro del área de cobertura. Nulos solo en municipios cargados antes de
    # que existiera la cobertura: sin centro no pueden recibir reportes nuevos.
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
    coverage_radius_km = models.DecimalField(
        _("coverage radius (km)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distancia desde el centro dentro de la cual llegan los reportes."),
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
        """Si puede resolver reportes por cercanía."""
        return (
            self.latitude is not None
            and self.longitude is not None
            and self.coverage_radius_km is not None
        )
