from functools import cached_property

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

from urbancheck.municipalities.api.serializers import MunicipalitySerializer
from urbancheck.municipalities.services import OutOfCoverageError
from urbancheck.municipalities.services import find_covering_municipality
from urbancheck.municipalities.services import resolve_municipality_for
from urbancheck.notifications.services import notify_new_comment
from urbancheck.notifications.services import notify_resolution_appealed
from urbancheck.reports.collective_validation import evaluate as evaluate_collective_validation
from urbancheck.reports.geo import parse_coordinates
from urbancheck.reports.geocoding import geocode_one
from urbancheck.reports.geocoding import reverse_geocode
from urbancheck.reports.geocoding import search_addresses
from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.resolution import appeal_resolution
from urbancheck.reports.services import GuardRejectedError
from urbancheck.reports.services import TransitionError
from urbancheck.reports.state_machine import APPEAL_LIMIT_MESSAGE
from urbancheck.reports.state_machine import MAX_APPEALS_PER_REPORT
from urbancheck.users.api.operator_permissions import ExcludesOperator

from .filters import apply_report_filters
from .permissions import CanDeleteComment
from .permissions import IsAuthorOrReadOnly
from .permissions import ParticipatesAsCitizen
from .serializers import CommentSerializer
from .serializers import ReportCreateSerializer
from .serializers import ReportDetailSerializer
from .serializers import ReportListSerializer
from .serializers import ReportMapSerializer
from .serializers import ReportUpdateSerializer
from .serializers import ResolutionAppealCreateSerializer
from .transition_responses import transition_error_response

# Estados que dejan de ser visibles en el feed y en el mapa público: el reporte
# ya no es un problema activo (US-013). El autor sigue viéndolos en "mis
# reportes" y en el detalle, que es a donde lo lleva la notificación del cambio.
INACTIVE_PUBLIC_STATUSES = [Report.Status.CANCELADO, Report.Status.ARCHIVADO]
INACTIVE_MAP_STATUSES = INACTIVE_PUBLIC_STATUSES

# Todo estado distinto de PENDIENTE_VALIDACION se alcanza pasando por un
# validador —validando o rechazando—, así que el texto vale para todos.
EDIT_BLOCKED_MESSAGE = "Este reporte ya pasó por un validador y no puede modificarse."
DELETE_BLOCKED_MESSAGE = "Este reporte ya pasó por un validador y no puede eliminarse."

# Apelar el cierre es del **autor** y de nadie más (US-048, escenario 7).
# Habilitar a cualquier vecino a objetar el cierre de un reporte ajeno es otra
# funcionalidad, prevista en el documento de Alcance y fuera de esta historia.
NOT_THE_AUTHOR_MESSAGE = (
    "Solo el autor del reporte puede objetar el cierre de su reclamo."
)
APPEAL_WINDOW_CLOSED_MESSAGE = (
    "El plazo para objetar el cierre venció y la resolución quedó confirmada."
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

        ``ExcludesOperator`` sí vale para todas: el alcance del operario es su
        bandeja y nada más (US-045), así que esta superficie entera —feed, mapa,
        detalle, comentarios— le responde ``403``.
        """
        if self.action in {"update", "partial_update", "destroy"}:
            return [IsAuthenticated(), ExcludesOperator(), IsAuthorOrReadOnly()]
        if self._is_citizen_participation():
            return [IsAuthenticated(), ExcludesOperator(), ParticipatesAsCitizen()]
        return [IsAuthenticated(), ExcludesOperator()]

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

    def _scoping_origin(self) -> tuple[float, float] | None:
        """Ubicación desde la que el cliente pide ver los reportes.

        La app móvil manda la posición del vecino para que el feed y el mapa
        muestren únicamente lo que pasa en el municipio donde está parado. Solo
        acota la lectura pública: "mis reportes" es del autor y lo sigue viendo
        esté donde esté, y el detalle de un reporte tampoco depende de dónde se
        abra.

        Sin coordenadas no se acota nada, que es el comportamiento anterior: un
        cliente viejo sigue funcionando igual.
        """
        if self.action not in {"list", "map"} or self._is_own_listing():
            return None
        return parse_coordinates(self.request.query_params)

    @cached_property
    def covering_municipality(self):
        """Municipalidad cuyo radio contiene al vecino; ``None`` si ninguna.

        Es la misma resolución que decide la jurisdicción de un reporte nuevo,
        a propósito: leer y escribir tienen que coincidir sobre qué municipio
        cubre un lugar, o el vecino reportaría un bache que después no ve.

        Memoizada porque la miran el queryset y la respuesta, y la vista dura lo
        que dura la petición.
        """
        origin = self._scoping_origin()
        if origin is None:
            return None
        return find_covering_municipality(*origin)

    def _is_own_listing(self) -> bool:
        return self.request.query_params.get("mine") == "true"

    def get_queryset(self):
        user = self.request.user
        qs = (
            Report.objects.select_related("author")
            .prefetch_related("resolution_evidences", "resolution_appeals")
            .annotate(
                like_count=Count("likes", distinct=True),
                comment_count=Count("comments", distinct=True),
                is_liked=Exists(Like.objects.filter(report=OuterRef("pk"), user=user)),
                # Alimenta el distintivo de "el municipio respondió" del feed
                # (US-024) sin traer el hilo entero por fila.
                official_response_count=Count("official_responses", distinct=True),
            )
            .order_by("-created_at")
        )
        # El validador solo ve su jurisdicción, en todas las acciones: pedir por
        # id un reporte de otro municipio devuelve 404 porque no existe para él.
        if user.sees_only_own_municipality:
            qs = qs.for_user(user)

        if self._is_own_listing():
            qs = qs.filter(author=user)
        elif self.action in {"list", "map"}:
            qs = qs.exclude(status__in=INACTIVE_PUBLIC_STATUSES)
            if self._scoping_origin() is not None:
                # Fuera de toda cobertura no hay municipio al que mirar, y el
                # feed queda vacío. Se dice explícito y no con
                # ``filter(municipality=None)``: eso significaría "los reportes
                # sin municipio", que es otra cosa.
                municipality = self.covering_municipality
                qs = qs.covered_by(municipality) if municipality else qs.none()
        return apply_report_filters(qs, self.request.query_params, requesting_user=user)

    def _coverage_payload(self) -> dict | None:
        """Cobertura resuelta, o ``None`` si el cliente no mandó ubicación.

        Sin este dato el cliente no puede distinguir dos situaciones que se
        parecen —ambas llegan con cero reportes— y que se le explican al vecino
        de forma muy distinta: que todavía no haya reportes en su municipio, o
        que esté fuera del área de toda municipalidad adherida.

        La usan el feed y el mapa: las dos pantallas se acotan igual, así que
        tienen que poder explicar igual por qué vienen vacías.
        """
        if self._scoping_origin() is None:
            return None
        municipality = self.covering_municipality
        return {
            "in_coverage": municipality is not None,
            "municipality": (
                MunicipalitySerializer(
                    municipality,
                    context=self.get_serializer_context(),
                ).data
                if municipality is not None
                else None
            ),
        }

    def list(self, request, *args, **kwargs):
        """Suma al feed la cobertura resuelta, cuando el cliente mandó ubicación."""
        response = super().list(request, *args, **kwargs)
        coverage = self._coverage_payload()
        if coverage is not None:
            response.data["coverage"] = coverage
        return response

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
        ``status``, ``search``) y, como él, se acota al municipio que cubre la
        ubicación del vecino cuando esta viaja en ``latitude``/``longitude``.
        """
        qs = (
            self.get_queryset()
            .filter(latitude__isnull=False, longitude__isnull=False)
            .exclude(status__in=INACTIVE_MAP_STATUSES)
        )
        serializer = ReportMapSerializer(qs, many=True, context={"request": request})
        payload = {"results": serializer.data}
        coverage = self._coverage_payload()
        if coverage is not None:
            payload["coverage"] = coverage
        return Response(payload)

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
            # US-040: el umbral se evalúa **al persistir el me gusta**, no en un
            # job periódico. Un reporte que llegó a las confirmaciones
            # necesarias tiene que pasar a Reportado en el momento, no horas
            # después. La función decide sola si hay algo que hacer.
            evaluate_collective_validation(report)
        else:
            Like.objects.filter(report=report, user=request.user).delete()
            liked = False
            code = status.HTTP_200_OK
            # Retirar un me gusta **no** revierte una validación colectiva ya
            # ejecutada (escenario 5): por eso acá no se evalúa nada.
        report.refresh_from_db()
        return Response(
            {
                "liked": liked,
                "like_count": report.likes.count(),
                # El cliente necesita saber si el reporte cambió de estado en
                # esta misma operación para refrescar el detalle y el feed.
                "status": report.status,
            },
            status=code,
        )

    @action(detail=True, methods=["post"])
    def appeal(self, request, pk=None):
        """El autor objeta el cierre de su reporte (US-048).

        Las tres condiciones se comprueban en tres capas distintas, a propósito:
        la autoría acá —es un permiso—, el estado en la máquina de estados, y el
        tope de una apelación en la guarda de la transición. Ninguna vive en dos
        lugares.
        """
        report = self.get_object()
        if report.author_id != request.user.id:
            raise PermissionDenied(NOT_THE_AUTHOR_MESSAGE)

        serializer = ResolutionAppealCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            appeal = appeal_resolution(
                report,
                author=request.user,
                reason=serializer.validated_data["reason"],
                photo=serializer.validated_data["photo"],
            )
        except GuardRejectedError as error:
            # El tope, cuando el reporte está en el estado correcto: la guarda
            # ya trae el motivo exacto.
            return transition_error_response(error)
        except TransitionError as error:
            # Dos caminos distintos dejan el reporte en *Resuelto*, y el vecino
            # merece saber por cuál se quedó afuera: o se le venció el plazo, o
            # ya usó su única objeción y el segundo cierre fue definitivo.
            # Decir el motivo equivocado lo manda a discutir lo que no es.
            #
            # La **regla** sigue viviendo en la máquina de estados —acá se lee
            # su constante, no se reimplementa el tope—; lo que se elige es la
            # explicación, que la guarda no llega a dar porque el estado ya
            # falló antes.
            if report.status == Report.Status.RESUELTO:
                exhausted = report.appeal_count >= MAX_APPEALS_PER_REPORT
                return Response(
                    {
                        "detail": (
                            APPEAL_LIMIT_MESSAGE
                            if exhausted
                            else APPEAL_WINDOW_CLOSED_MESSAGE
                        ),
                        "current_status": report.status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return transition_error_response(error)

        notify_resolution_appealed(appeal)
        report.refresh_from_db()
        return Response(
            ReportDetailSerializer(report, context={"request": request}).data,
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
    """Borrado de comentarios (US-009).

    Lo puede borrar su autor —uno se arrepiente de lo que escribió— o el autor
    del reporte, que modera lo que queda colgado de su publicación.

    Vive aparte del ReportViewSet porque el recurso se identifica por su propio id
    (``DELETE /api/comments/{id}/``) y no depende del reporte contenedor.
    """

    permission_classes = [IsAuthenticated, CanDeleteComment]
    serializer_class = CommentSerializer
    queryset = Comment.objects.select_related("author", "report")
