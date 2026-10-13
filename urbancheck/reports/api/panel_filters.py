"""Filtros del listado del panel municipal (US-012).

Se resuelven con ``django-filter`` porque el juego es grande: selección
múltiple, rango de fechas y ordenamiento. El feed ciudadano sigue con sus
filtros a mano en ``filters.py``, que responden a otra pregunta.

Los filtros se combinan con AND entre sí y con OR dentro de una misma selección
múltiple.

``municipality`` es para el administrador de la plataforma, que ve todas las
jurisdicciones y necesita poder acotar. **No es un agujero en la jurisdicción**:
el filtro se aplica sobre el queryset que ya devolvió
``JurisdictionScopedMixin``, así que un agente que lo pida con un municipio
ajeno recibe una lista vacía, no la del otro municipio.
"""

from django.db.models import OuterRef
from django.db.models import Subquery
from django_filters import rest_framework as filters

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.state_machine import VALIDATOR_DECISIONS
from urbancheck.reports.state_machine import Origin


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Acepta ``?status=reportado,en_proceso`` (OR dentro del filtro)."""


class PanelReportFilterSet(filters.FilterSet):
    municipality = filters.NumberFilter(field_name="municipality_id")
    # Todo lo que reportó una persona, para el perfil que abre el panel desde
    # su nombre. Como el resto, se aplica sobre el queryset ya acotado por
    # jurisdicción: un agente ve lo que esa persona reportó **en su municipio**,
    # nunca su actividad en otro.
    author = filters.NumberFilter(field_name="author_id")
    # Lo que decidió un validador, para el perfil que abre el panel desde su
    # nombre en el detalle. Mismo criterio que ``author``: se aplica sobre el
    # queryset ya acotado por jurisdicción.
    validated_by = filters.NumberFilter(method="filter_validated_by")
    # Lo que cerró un operario, para el perfil que el panel abre desde su nombre
    # en el hilo de resolución (US-046). Mismo criterio que ``author`` y
    # ``validated_by``: se aplica sobre el queryset ya acotado por jurisdicción,
    # así que un agente ve lo que ese operario cerró **en su municipio**.
    closed_by = filters.NumberFilter(method="filter_closed_by")
    status = CharInFilter(field_name="status", lookup_expr="in")
    category = CharInFilter(field_name="category", lookup_expr="in")
    created_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    # "Zona" no existe como entidad en el modelo y nadie la definió: se resuelve
    # como búsqueda de texto sobre la dirección. Decisión documentada en el
    # README; no se implementa filtrado por polígonos.
    zone = filters.CharFilter(field_name="address", lookup_expr="icontains")

    ordering = filters.OrderingFilter(
        fields=(
            ("created_at", "created_at"),
            ("like_count", "like_count"),
        ),
    )

    def filter_validated_by(self, queryset, name, value):
        """Reportes en los que esa persona salió a decidir en terreno.

        Anota además **qué** decidió y cuándo, porque el estado actual del
        reporte no lo dice: uno validado y cancelado después por el municipio
        figura como *Cancelado*, igual que uno que el validador rechazó. Sin la
        anotación, la lista del perfil mostraría lo segundo donde pasó lo
        primero.

        Se toma la decisión más vieja, por lo mismo que en el detalle: un
        reporte reactivado vuelve a pasar por *Reportado*.
        """
        decisions = ReportStatusHistory.objects.filter(
            report=OuterRef("pk"),
            changed_by_id=value,
            # Por el origen y no por la forma de la transición: desde US-040 la
            # validación colectiva sale del mismo estado y llega al mismo, sin
            # que haya habido un validador. Acá el filtro por ``changed_by`` ya
            # la dejaba afuera —no tiene responsable—, pero el criterio tiene
            # que ser el mismo que el del detalle o los dos van a divergir.
            origin=Origin.VALIDACION_TERRENO,
            status__in=list(VALIDATOR_DECISIONS),
        ).order_by("created_at")

        return queryset.annotate(
            validation_status=Subquery(decisions.values("status")[:1]),
            validation_decided_at=Subquery(decisions.values("created_at")[:1]),
        ).filter(validation_status__isnull=False)

    def filter_closed_by(self, queryset, name, value):
        """Reportes que esa persona cerró en terreno.

        Se filtra por la **evidencia** y no por el historial de estados: quién
        cerró es un dato propio del parte de trabajo, y deducirlo de la forma de
        la transición es justamente el error que US-040 destapó en la validación
        colectiva.

        Va por subconsulta y no por ``filter()`` sobre la relación inversa: un
        reporte reabierto por apelación y vuelto a cerrar tiene dos evidencias
        del mismo operario, y el ``JOIN`` devolvería la fila duplicada.

        Se anota el cierre **más reciente**, al revés que ``validated_by``: la
        decisión del validador es la primera —un reporte reactivado vuelve a
        pasar por *Reportado*—, mientras que de un cierre interesa el último,
        que es el que está vigente.
        """
        closures = ResolutionEvidence.objects.filter(
            report=OuterRef("pk"),
            operator_id=value,
        ).order_by("-created_at")

        return queryset.annotate(
            closure_closed_at=Subquery(closures.values("created_at")[:1]),
        ).filter(closure_closed_at__isnull=False)

    class Meta:
        model = Report
        fields = [
            "municipality",
            "author",
            "validated_by",
            "closed_by",
            "status",
            "category",
            "created_from",
            "created_to",
            "zone",
        ]
