"""API de validación en terreno (US-036 y US-037).

Superficie propia, con el mixin de jurisdicción de US-034: un validador solo ve
y solo puede operar sobre reportes de su municipalidad, y eso lo garantiza el
queryset, no un ``if`` dentro de cada acción.
"""

from django.conf import settings
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.geo import distance_expression
from urbancheck.reports.geo import haversine_meters
from urbancheck.reports.models import Report
from urbancheck.reports.services import TransitionError
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import Actor
from urbancheck.users.api.validation_permissions import CanValidate

from .mixins import JurisdictionScopedMixin
from .transition_responses import transition_error_response
from .validation_serializers import PendingValidationSerializer

MISSING_COORDINATES_MESSAGE = (
    "Necesitamos tu ubicación para validar un reporte en terreno."
)
TOO_FAR_CODE = "too_far"


def _parse_coordinates(data) -> tuple[float, float] | None:
    """Lee ``latitude``/``longitude`` de un dict de request. ``None`` si faltan."""
    try:
        return float(data["latitude"]), float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


class ValidationReportViewSet(
    JurisdictionScopedMixin,
    ListModelMixin,
    RetrieveModelMixin,
    GenericViewSet,
):
    """Bandeja de pendientes y acciones de validación."""

    permission_classes = [IsAuthenticated, CanValidate]
    serializer_class = PendingValidationSerializer
    queryset = Report.objects.select_related("author", "municipality")

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            queryset = queryset.filter(status=Report.Status.PENDIENTE_VALIDACION)
        return self._with_distance(queryset)

    def _with_distance(self, queryset):
        """Anota la distancia y ordena por cercanía **en la base**.

        Sin coordenadas la pantalla igual tiene que funcionar: se ordena por
        fecha y la distancia viaja nula. Es el caso de un validador que no
        concedió el permiso de ubicación.
        """
        origin = _parse_coordinates(self.request.query_params)
        if origin is None:
            return queryset.order_by("-created_at")
        latitude, longitude = origin
        return (
            queryset.exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .annotate(distance_meters=distance_expression(latitude, longitude))
            .order_by("distance_meters")
        )

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        """Pendiente de validación → Reportado, estando en el lugar."""
        return self._validate_in_place(request, operation="validar")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Pendiente de validación → Cancelado. Exige motivo."""
        return self._validate_in_place(request, operation="rechazar")

    def _validate_in_place(self, request, *, operation: str) -> Response:
        report = self.get_object()

        origin = _parse_coordinates(request.data)
        if origin is None:
            return Response(
                {"detail": MISSING_COORDINATES_MESSAGE},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        too_far = self._distance_check(report, origin)
        if too_far is not None:
            return too_far

        try:
            apply_transition(
                report,
                operation,
                actor=Actor.VALIDATOR,
                changed_by=request.user,
                reason=request.data.get("reason", ""),
            )
        except TransitionError as error:
            return transition_error_response(error)

        report.refresh_from_db()
        return Response(
            PendingValidationSerializer(report, context={"request": request}).data,
        )

    def _distance_check(self, report: Report, origin: tuple[float, float]):
        """Rechaza la acción si el validador no está en el lugar del problema.

        El error es distinguible y viaja con la distancia real, para que el
        móvil pueda decir "estás a 320 m" en lugar de un mensaje genérico.
        """
        if report.latitude is None or report.longitude is None:
            return None

        distance = haversine_meters(
            origin[0],
            origin[1],
            report.latitude,
            report.longitude,
        )
        radius = settings.VALIDATION_RADIUS_METERS
        if distance <= radius:
            return None

        return Response(
            {
                "code": TOO_FAR_CODE,
                "detail": (
                    "Tenés que estar en el lugar del problema para validarlo: "
                    f"estás a {round(distance)} m y el límite es de {radius} m."
                ),
                "distance_meters": round(distance, 1),
                "radius_meters": radius,
            },
            status=http_status.HTTP_400_BAD_REQUEST,
        )
