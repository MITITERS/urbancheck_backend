from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.services import deactivate_municipality
from urbancheck.reports.api.panel_filters import PanelReportFilterSet
from urbancheck.reports.api.panel_serializers import PanelReportListSerializer
from urbancheck.reports.api.statistics_views import STATISTICS_PARAMETERS
from urbancheck.reports.api.statistics_views import StatisticsSerializer
from urbancheck.reports.api.statistics_views import statistics_response
from urbancheck.reports.models import Report
from urbancheck.reports.moderation import pending_content_complaints
from urbancheck.users.api.permissions import IsPlatformAdmin

from .serializers import MunicipalityReportMarkerSerializer
from .serializers import MunicipalitySerializer

# Estados que no se dibujan en el mapa público. El panel del administrador sí
# los muestra: está mirando la gestión del municipio, no el feed ciudadano.
DEACTIVATED_MESSAGE = "La municipalidad quedó dada de baja."


class MunicipalityViewSet(ModelViewSet):
    """CRUD de municipalidades, solo para el administrador de la plataforma.

    El borrado es **lógico**: un municipio con reportes o usuarios no se puede
    eliminar de la base sin perder historia, así que se lo desactiva. Deja de
    recibir reportes nuevos y de aparecer en el listado.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = MunicipalitySerializer

    def get_queryset(self):
        queryset = Municipality.objects.annotate(
            report_count=Count("reports", distinct=True),
            user_count=Count("users", distinct=True),
        )
        # Las dadas de baja siguen siendo accesibles por id —el detalle de una
        # baja reciente no debería romperse— pero no aparecen en el listado.
        if self.action == "list":
            queryset = queryset.active()
        return queryset

    def perform_destroy(self, instance):
        # La baja arrastra al personal y a las áreas operativas del municipio:
        # ver ``municipalities.services.deactivate_municipality``.
        self._deactivated = deactivate_municipality(instance)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        # Qué cayó con el municipio: son consecuencias que no se ven desde la
        # pantalla donde se ejecuta la baja, así que viajan en la respuesta para
        # que el panel pueda decirlas.
        return Response(
            {
                "detail": DEACTIVATED_MESSAGE,
                "deactivated_users": self._deactivated.users,
                "deactivated_areas": self._deactivated.areas,
            },
            status=status.HTTP_200_OK,
        )

    def _reports_queryset(self, municipality):
        """Reportes del municipio, con el mismo shape que usa el panel."""
        return (
            Report.objects.filter(municipality=municipality)
            .select_related("author", "municipality", "operational_area")
            .annotate(
                like_count=Count("likes", distinct=True),
                official_response_count=Count("official_responses", distinct=True),
                pending_complaint_count=pending_content_complaints(),
            )
            .order_by("-created_at")
        )

    @action(detail=True, methods=["get"])
    def reports(self, request, pk=None):
        """Listado paginado de los reportes de este municipio.

        Acepta los mismos filtros que el panel municipal, así que el
        administrador ve exactamente lo que ve el agente de ese municipio.
        """
        municipality = self.get_object()
        queryset = PanelReportFilterSet(
            request.query_params,
            queryset=self._reports_queryset(municipality),
            request=request,
        ).qs

        page = self.paginate_queryset(queryset)
        serializer = PanelReportListSerializer(
            page,
            many=True,
            context={"request": request},
        )
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"], url_path="reports/map")
    def report_markers(self, request, pk=None):
        """Marcadores del municipio, sin paginar.

        El mapa necesita todos los puntos de una, no una página; por eso va
        aparte del listado y con un payload mínimo.
        """
        municipality = self.get_object()
        # Consulta propia y no ``_reports_queryset``: un marcador no necesita el
        # autor ni el conteo de likes, y ``only()`` no convive con el
        # ``select_related`` de aquella.
        queryset = (
            Report.objects.filter(municipality=municipality)
            .filter(latitude__isnull=False, longitude__isnull=False)
            .only(
                "id",
                "number",
                "category",
                "status",
                "latitude",
                "longitude",
                "address",
            )
            .order_by("-created_at")
        )
        serializer = MunicipalityReportMarkerSerializer(queryset, many=True)
        return Response({"results": serializer.data})

    @extend_schema(parameters=STATISTICS_PARAMETERS, responses=StatisticsSerializer)
    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        """Las estadísticas de esta municipalidad (US-023, escenario 9).

        La misma respuesta y los mismos filtros que ve su agente, acotada al
        municipio de la ficha.
        """
        municipality = self.get_object()
        return statistics_response(
            request,
            Report.objects.filter(municipality=municipality),
        )
