from django.db.models import Count
from django.db.models import IntegerField
from django.db.models import OuterRef
from django.db.models import Subquery
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.geocoding import geocode_one
from urbancheck.reports.geocoding import search_addresses
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory

from .serializers import CommentSerializer
from .serializers import ReportCreateSerializer
from .serializers import ReportDetailSerializer
from .serializers import ReportListSerializer


class ReportViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        qs = Report.objects.annotate(
            like_count=Count("likes", distinct=True),
            comment_count=Count("comments", distinct=True),
        ).order_by("-created_at")
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(author=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ReportCreateSerializer
        if self.action == "retrieve":
            return ReportDetailSerializer
        return ReportListSerializer

    def perform_create(self, serializer):
        extra = {}
        # Fallback: si el usuario escribió una dirección a mano pero no eligió una
        # sugerencia (sin coordenadas), la geocodificamos en el servidor para que el
        # reporte tenga lat/lng y pueda ubicarse en el mapa.
        has_coords = (
            serializer.validated_data.get("latitude") is not None
            and serializer.validated_data.get("longitude") is not None
        )
        address = serializer.validated_data.get("address", "").strip()
        if not has_coords and address:
            match = geocode_one(address)
            if match:
                extra["latitude"] = match["latitude"]
                extra["longitude"] = match["longitude"]

        report = serializer.save(author=self.request.user, **extra)
        ReportStatusHistory.objects.create(
            report=report,
            status=Report.Status.PENDIENTE_VALIDACION,
            changed_by=self.request.user,
        )

    @action(detail=False, methods=["get"])
    def geocode(self, request):
        """Autocompletado de direcciones: GET /api/reports/geocode/?q=<texto>.

        Proxy cacheado hacia Nominatim. Devuelve
        ``{"results": [{"display_name", "latitude", "longitude"}, ...]}``.
        """
        query = request.query_params.get("q", "")
        results = search_addresses(query, limit=5)
        return Response({"results": results})

    @action(detail=True, methods=["post", "delete"])
    def like(self, request, pk=None):
        report = self.get_object()
        if request.method == "POST":
            Like.objects.get_or_create(report=report, user=request.user)
            return Response(status=status.HTTP_201_CREATED)
        Like.objects.filter(report=report, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], parser_classes=[JSONParser, MultiPartParser])
    def comments(self, request, pk=None):
        report = self.get_object()
        if request.method == "GET":
            qs = report.comments.select_related("author")
            serializer = CommentSerializer(qs, many=True, context={"request": request})
            return Response(serializer.data)
        serializer = CommentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(report=report, author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
