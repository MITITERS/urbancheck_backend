from django.db.models import Count
from django.db.models import Exists
from django.db.models import OuterRef
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import CreateModelMixin
from rest_framework.mixins import DestroyModelMixin
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.municipalities.services import OutOfCoverageError
from urbancheck.municipalities.services import resolve_municipality_for
from urbancheck.notifications.services import notify_new_comment
from urbancheck.reports.geocoding import geocode_one
from urbancheck.reports.geocoding import reverse_geocode
from urbancheck.reports.geocoding import search_addresses
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory

from .filters import apply_report_filters
from .permissions import IsAuthorOrReadOnly
from .permissions import ParticipatesAsCitizen
from .serializers import CommentSerializer
from .serializers import ReportCreateSerializer
from .serializers import ReportDetailSerializer
from .serializers import ReportListSerializer
from .serializers import ReportMapSerializer
from .serializers import ReportUpdateSerializer

# Estados que dejan de ser visibles en el feed y en el mapa público: el reporte
# ya no es un problema activo (US-013). El autor sigue viéndolos en "mis
# reportes" y en el detalle, que es a donde lo lleva la notificación del cambio.
INACTIVE_PUBLIC_STATUSES = [Report.Status.CANCELADO, Report.Status.ARCHIVADO]
INACTIVE_MAP_STATUSES = INACTIVE_PUBLIC_STATUSES

EDIT_BLOCKED_MESSAGE = (
    "Este reporte ya está siendo gestionado por el municipio y no puede modificarse."
)
DELETE_BLOCKED_MESSAGE = (
    "Este reporte ya está siendo gestionado por el municipio y no puede eliminarse."
)


class ReportViewSet(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, JSONParser]

    def get_permissions(self):
        """Permisos por acción: autoría para editar/borrar, rol para participar.

        La restricción de autoría no puede vivir en ``permission_classes`` de
        la clase: ``like`` y ``comments`` también usan ``get_object()`` con
        métodos no seguros sobre reportes ajenos, que es exactamente lo que
        debe poder hacer un vecino.
        """
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsAuthenticated(), IsAuthorOrReadOnly()]
        if self._is_citizen_participation():
            return [IsAuthenticated(), ParticipatesAsCitizen()]
        return [IsAuthenticated()]

    def _is_citizen_participation(self) -> bool:
        """Si la petición es un aporte de vecino: reportar, comentar o gustar.

        ``like`` y ``comments`` atienden más de un método bajo la misma acción,
        así que no alcanza con mirar ``self.action``. Solo se restringe el alta:

        - ``GET /comments/`` es lectura, y el personal municipal tiene que poder
          leer lo que comentan los vecinos sobre lo que va a resolver.
        - ``DELETE /like/`` deshace. Bloquearlo dejaría trabado un me gusta
          anterior a esta regla, sin forma de sacarlo.
        """
        if self.action == "create":
            return True
        return self.action in {"like", "comments"} and self.request.method == "POST"

    def get_queryset(self):
        user = self.request.user
        qs = (
            Report.objects.select_related("author")
            .annotate(
                like_count=Count("likes", distinct=True),
                comment_count=Count("comments", distinct=True),
                is_liked=Exists(Like.objects.filter(report=OuterRef("pk"), user=user)),
            )
            .order_by("-created_at")
        )
        # El validador solo ve su jurisdicción, en todas las acciones: pedir por
        # id un reporte de otro municipio devuelve 404 porque no existe para él.
        if user.sees_only_own_municipality:
            qs = qs.for_user(user)

        is_own_listing = self.request.query_params.get("mine") == "true"
        if is_own_listing:
            qs = qs.filter(author=user)
        elif self.action in {"list", "map"}:
            qs = qs.exclude(status__in=INACTIVE_PUBLIC_STATUSES)
        return apply_report_filters(qs, self.request.query_params, requesting_user=user)

    def get_serializer_class(self):
        if self.action == "create":
            return ReportCreateSerializer
        if self.action in {"update", "partial_update"}:
            return ReportUpdateSerializer
        if self.action == "map":
            return ReportMapSerializer
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
        elif has_coords and not address:
            # Camino inverso: el reporte llega del GPS, solo con coordenadas. Sin
            # texto de dirección la búsqueda por calle, barrio o localidad
            # (US-020) nunca podría encontrarlo, así que la resolvemos acá.
            extra["address"] = reverse_geocode(
                serializer.validated_data["latitude"],
                serializer.validated_data["longitude"],
            )

        # US-034: la jurisdicción se resuelve en el servidor por área de
        # cobertura. Si el cliente mandó una municipalidad, se ignora.
        latitude = extra.get("latitude", serializer.validated_data.get("latitude"))
        longitude = extra.get("longitude", serializer.validated_data.get("longitude"))
        try:
            municipality = resolve_municipality_for(latitude, longitude)
        except OutOfCoverageError as error:
            raise ValidationError({"location": error.message}) from error

        report = serializer.save(
            author=self.request.user,
            municipality=municipality,
            **extra,
        )
        ReportStatusHistory.objects.create(
            report=report,
            status=Report.Status.PENDIENTE_VALIDACION,
            changed_by=self.request.user,
        )

    def perform_update(self, serializer):
        """US-018: editar solo mientras el municipio no tomó el reporte."""
        if not serializer.instance.is_editable:
            raise PermissionDenied(EDIT_BLOCKED_MESSAGE)
        serializer.save(edited_at=timezone.now())

    def perform_destroy(self, instance):
        """US-019: borrado definitivo, y solo si todavía no está en gestión."""
        if not instance.is_editable:
            raise PermissionDenied(DELETE_BLOCKED_MESSAGE)
        instance.delete()

    def update(self, request, *args, **kwargs):
        """Devuelve el detalle completo tras editar, para que el cliente refresque."""
        super().update(request, *args, **kwargs)
        instance = self.get_object()
        serializer = ReportDetailSerializer(instance, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def map(self, request):
        """Marcadores geolocalizados: GET /api/reports/map/.

        Sin paginar y con payload mínimo: el mapa necesita todos los marcadores de
        una, no una página. Acepta los mismos filtros que el feed (``category``,
        ``status``, ``search``).
        """
        qs = (
            self.get_queryset()
            .filter(latitude__isnull=False, longitude__isnull=False)
            .exclude(status__in=INACTIVE_MAP_STATUSES)
        )
        serializer = ReportMapSerializer(qs, many=True, context={"request": request})
        return Response({"results": serializer.data})

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
        """Alterna el like y devuelve el estado resultante (US-008).

        Responder con ``liked`` y ``like_count`` evita que el cliente tenga que
        adivinar el contador o pedir el reporte de nuevo.
        """
        report = self.get_object()
        if request.method == "POST":
            Like.objects.get_or_create(report=report, user=request.user)
            liked = True
            code = status.HTTP_201_CREATED
        else:
            Like.objects.filter(report=report, user=request.user).delete()
            liked = False
            code = status.HTTP_200_OK
        return Response(
            {"liked": liked, "like_count": report.likes.count()},
            status=code,
        )

    @action(
        detail=True,
        methods=["get", "post"],
        parser_classes=[JSONParser, MultiPartParser],
    )
    def comments(self, request, pk=None):
        report = self.get_object()
        if request.method == "GET":
            qs = report.comments.select_related("author")
            serializer = CommentSerializer(qs, many=True, context={"request": request})
            return Response(serializer.data)
        serializer = CommentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(report=report, author=request.user)
        # US-009: el autor del reporte recibe un aviso por cada comentario nuevo.
        notify_new_comment(comment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CommentViewSet(DestroyModelMixin, GenericViewSet):
    """Borrado de comentarios propios (US-009).

    Vive aparte del ReportViewSet porque el recurso se identifica por su propio id
    (``DELETE /api/comments/{id}/``) y no depende del reporte contenedor.
    """

    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly]
    serializer_class = CommentSerializer
    queryset = Comment.objects.select_related("author", "report")
