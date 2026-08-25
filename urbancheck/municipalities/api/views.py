from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from urbancheck.municipalities.models import Municipality
from urbancheck.reports.api.panel_filters import PanelReportFilterSet
from urbancheck.reports.api.panel_serializers import PanelReportListSerializer
from urbancheck.reports.models import Report
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
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"detail": DEACTIVATED_MESSAGE}, status=status.HTTP_200_OK)

    def _reports_queryset(self, municipality):
        """Reportes del municipio, con el mismo shape que usa el panel."""
        return (
            Report.objects.filter(municipality=municipality)
            .select_related("author", "municipality")
            .annotate(like_count=Count("likes", distinct=True))
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
            .only("id", "category", "status", "latitude", "longitude", "address")
            .order_by("-created_at")
        )
        serializer = MunicipalityReportMarkerSerializer(queryset, many=True)
        return Response({"results": serializer.data})
