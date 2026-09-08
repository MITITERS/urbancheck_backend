"""Bandeja de trabajo del operario (US-045).

Superficie propia, como la del panel y la de validación: el área y la
municipalidad se resuelven desde el usuario autenticado y **nunca** se aceptan
como parámetro del cliente.
"""

from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Prefetch
from django.db.models import Q
from django.db.models import Subquery
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.parsers import FormParser
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.models import Comment
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.resolution import TooFarError
from urbancheck.reports.resolution import register_resolution
from urbancheck.reports.services import TransitionError
from urbancheck.users.api.operator_permissions import CanWorkAsOperator

from .pagination import PanelPagination
from .serializers import OperatorHistorySerializer
from .serializers import ReportDetailSerializer
from .serializers import ReportListSerializer
from .serializers import ResolutionCreateSerializer
from .transition_responses import transition_error_response

ALREADY_CLOSED_MESSAGE = (
    "Este reporte ya fue cerrado. Actualizá la bandeja para ver el estado real."
)
TOO_FAR_CODE = "too_far"


class OperatorReportViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """Los reportes asignados al área del operario, su detalle y su historial.

    **No** hereda de ``JurisdictionScopedMixin``: el recorte por área es más
    estrecho que el recorte por municipalidad y ya lo implica, así que aplicar
    los dos sería escribir la misma restricción dos veces. Si el área del
    operario cambia de municipio —cosa que el modelo impide—, el filtro sigue
    siendo correcto porque parte del área y no de la jurisdicción.

    El filtro por área acota la bandeja, el detalle y el cierre, y el de estado
    solo la bandeja. Así, pedir por id un reporte de otra área responde ``404``
    (escenario 7) y el detalle de uno que acaba de salir de *En proceso* sigue
    abriéndose en lugar de romperse en la mano del operario.

    El historial es la excepción y se recorta por otra cosa —quién registró el
    cierre—, porque es un registro de lo que hizo la persona y no de lo que
    tiene a cargo el área hoy.

    La respuesta reutiliza los serializers públicos: el operario no es personal
    de auditoría y no recibe los campos restringidos del panel.
    """

    permission_classes = [IsAuthenticated, CanWorkAsOperator]
    pagination_class = PanelPagination
    # El cierre sube una foto: la acción necesita ``multipart``. El resto de la
    # superficie sigue aceptando JSON, que es lo que usa la lista.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def closed_by_me(self):
        """Los cierres registrados por el operario de la sesión.

        Como ``Subquery`` y no como ``filter()`` sobre la relación inversa: un
        reporte reabierto por apelación y vuelto a cerrar tiene **dos**
        evidencias del mismo operario, y el ``JOIN`` lo devolvería duplicado.
        """
        return ResolutionEvidence.objects.filter(
            report=OuterRef("pk"),
            operator=self.request.user,
        ).order_by("-created_at")

    def get_queryset(self):
        queryset = (
            Report.objects.select_related("author", "municipality")
            .prefetch_related(
                Prefetch("comments", queryset=Comment.objects.select_related("author")),
                Prefetch(
                    "status_history",
                    queryset=ReportStatusHistory.objects.select_related("changed_by"),
                ),
                Prefetch(
                    "official_responses",
                    queryset=OfficialResponse.objects.select_related("municipality"),
                ),
                Prefetch(
                    "resolution_evidences",
                    queryset=ResolutionEvidence.objects.select_related(
                        "operational_area",
                    ),
                ),
                "resolution_appeals",
            )
            .annotate(
                like_count=Count("likes", distinct=True),
                comment_count=Count("comments", distinct=True),
                official_response_count=Count("official_responses", distinct=True),
            )
        )
        if self.action == "history":
            # El historial **no** se acota por el área actual del operario, a
            # propósito: la evidencia guarda el área del momento del cierre
            # justamente para que un traslado posterior no reescriba quién se
            # hizo cargo (US-044, escenario 5), y filtrar por el área de hoy le
            # borraría del historial el trabajo que sí hizo. El recorte por
            # autoría del cierre es más estrecho que el del área, no más ancho.
            return (
                queryset.annotate(
                    resolved_at=Subquery(self.closed_by_me().values("created_at")[:1]),
                )
                .filter(resolved_at__isnull=False)
                # Lo último cerrado primero: al revés que la bandeja, porque
                # esto es un registro de lo hecho y no una cola de pendientes.
                .order_by("-resolved_at")
            )

        area_scope = Q(operational_area_id=self.request.user.operational_area_id)
        if self.action == "retrieve":
            # El detalle acepta además lo que cerró él mismo, para que toda fila
            # del historial se pueda abrir. Sin esto, al operario trasladado se
            # le listaría un trabajo que después responde 404 al tocarlo.
            queryset = queryset.filter(
                area_scope | Q(pk__in=self.closed_by_me().values("report_id")),
            )
        else:
            # El resto de la superficie —incluido el cierre— sigue acotado al
            # área actual y nada más: haber cerrado un reporte alguna vez no
            # habilita a volver a operarlo desde otra área.
            queryset = queryset.filter(area_scope)

        if self.action == "list":
            # Solo trabajo vigente, y lo más demorado primero: la bandeja es una
            # cola de tareas, no un archivo. El filtro va en el queryset base y
            # no en la serialización, para que el paginado cuente lo correcto.
            queryset = queryset.filter(status=Report.Status.EN_PROCESO).order_by(
                "area_assigned_at",
                "created_at",
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return ReportListSerializer
        if self.action == "history":
            return OperatorHistorySerializer
        if self.action == "resolve":
            return ResolutionCreateSerializer
        return ReportDetailSerializer

    @action(detail=False, methods=["get"])
    def history(self, request):
        """Los trabajos que este operario cerró (US-046).

        El equivalente de «Mis reportes» del vecino para una cuenta de trabajo:
        el vecino ve lo que reportó, el operario lo que resolvió. Va como acción
        propia y no como un filtro del listado porque la bandeja tiene que poder
        seguir siendo exactamente el trabajo pendiente, sin un parámetro del
        cliente que la convierta en otra cosa.

        El estado que se muestra es el **actual**: un cierre que el autor objetó
        vuelve a *En proceso* (US-048) y tiene que verse así acá, en lugar de
        quedar como resuelto en el historial de quien lo cerró.
        """
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """El operario registra la resolución del trabajo (US-046).

        El queryset ya dejó afuera los reportes de otras áreas —responden
        ``404``—, así que acá solo queda verificar lo que depende del estado y
        del lugar. El doble cierre y el estado inválido caen los dos en la misma
        comprobación: si el reporte no está *En proceso*, no hay nada que
        cerrar.
        """
        report = self.get_object()
        if report.status != Report.Status.EN_PROCESO:
            return Response(
                {
                    "detail": (
                        ALREADY_CLOSED_MESSAGE
                        if report.status == Report.Status.RESUELTO_PENDIENTE
                        else "Solo se puede cerrar un reporte en gestión."
                    ),
                    "current_status": report.status,
                },
                status=http_status.HTTP_409_CONFLICT,
            )

        serializer = ResolutionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            register_resolution(
                report,
                operator=request.user,
                photo=data["photo"],
                description=data["description"],
                latitude=data["latitude"],
                longitude=data["longitude"],
            )
        except TooFarError as error:
            # Error distinguible y con la distancia real, igual que en la
            # validación en terreno de US-036: la app dice "estás a 320 m".
            return Response(
                {
                    "code": TOO_FAR_CODE,
                    "detail": (
                        "Tenés que estar en el lugar del problema para cerrarlo: "
                        f"estás a {round(error.distance)} m y el límite es de "
                        f"{error.radius} m."
                    ),
                    "distance_meters": round(error.distance, 1),
                    "radius_meters": error.radius,
                },
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        except TransitionError as error:
            return transition_error_response(error)

        report.refresh_from_db()
        # El aviso al autor cuelga del mismo mecanismo que el resto: lo emite la
        # señal de cambio de estado, así que acá no hay nada que disparar.
        detail = ReportDetailSerializer(report, context={"request": request})
        return Response(detail.data)
