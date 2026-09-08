"""API del panel municipal.

Superficie separada de la del feed ciudadano: acá toda consulta pasa por la
capa de jurisdicción de US-034, y el permiso de entrada es el rol municipal.
"""

from django.db.models import Count
from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.models import Comment
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportAreaAssignment
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.users.api.permissions import IsPanelUser

from .mixins import JurisdictionScopedMixin
from .pagination import PanelPagination
from .panel_actions import ReportTransitionActionsMixin
from .panel_filters import PanelReportFilterSet
from .panel_serializers import PanelReportDetailSerializer
from .panel_serializers import PanelReportListSerializer


class PanelReportViewSet(
    JurisdictionScopedMixin,
    ReportTransitionActionsMixin,
    ListModelMixin,
    RetrieveModelMixin,
    GenericViewSet,
):
    """Reportes que el usuario del panel puede gestionar.

    El agente municipal ve los de su municipio; el administrador de la
    plataforma, los de todos, y puede acotarlos con ``?municipality=<id>``.
    Quién cruza jurisdicciones lo decide ``JurisdictionScopedMixin``, no esta
    vista.

    El mixin de jurisdicción va primero en el MRO a propósito: lo último que se
    aplica sobre el queryset es el filtro por municipalidad.
    """

    permission_classes = [IsAuthenticated, IsPanelUser]
    pagination_class = PanelPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = PanelReportFilterSet
    # El conteo de likes viaja anotado, nunca calculado por fila, y es también
    # lo que permite ordenar por validación colectiva en la base.
    queryset = (
        Report.objects.select_related(
            "author",
            "municipality",
            "operational_area__municipality",
        )
        .prefetch_related(
            Prefetch("comments", queryset=Comment.objects.select_related("author")),
            Prefetch(
                "status_history",
                queryset=ReportStatusHistory.objects.select_related("changed_by"),
            ),
            Prefetch(
                "official_responses",
                queryset=OfficialResponse.objects.select_related(
                    "author",
                    "municipality",
                ),
            ),
            Prefetch(
                "area_assignments",
                queryset=ReportAreaAssignment.objects.select_related(
                    "area",
                    "previous_area",
                    "assigned_by",
                ),
            ),
            Prefetch(
                "resolution_evidences",
                queryset=ResolutionEvidence.objects.select_related(
                    "operator",
                    "operational_area",
                ),
            ),
            Prefetch(
                "resolution_appeals",
                queryset=ResolutionAppeal.objects.select_related(
                    "author",
                    "evidence__operator",
                    "evidence__operational_area",
                ),
            ),
        )
        .annotate(
            like_count=Count("likes", distinct=True),
            # Alimenta el indicador de "sin respuesta oficial" del listado
            # (US-024, escenario 13) sin traer el hilo por fila.
            official_response_count=Count("official_responses", distinct=True),
        )
        .order_by("-created_at")
    )

    def get_serializer_class(self):
        if self.action == "list":
            return PanelReportListSerializer
        return PanelReportDetailSerializer

    def get_detail_serializer(self, report, request) -> PanelReportDetailSerializer:
        """Usado por las acciones de transición para devolver el detalle nuevo."""
        return PanelReportDetailSerializer(report, context={"request": request})
