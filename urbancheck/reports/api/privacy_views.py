"""Bandeja de solicitudes por dato personal del administrador (US-043).

Es la **excepción deliberada** a la regla de que toda vista del panel hereda
``JurisdictionScopedMixin``: el difuminado es una obligación de la plataforma
bajo la Ley 25.326, no del municipio, y el administrador ve las solicitudes de
todas las municipalidades. Por lo mismo, un agente municipal recibe ``403`` y
no ``404`` (escenario 10): no se esconde que la solicitud existe, se le niega
resolverla.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.privacy import ComplaintAlreadyResolvedError
from urbancheck.reports.privacy import dismiss
from urbancheck.reports.privacy import remove_image
from urbancheck.users.api.permissions import IsPlatformAdmin

from .pagination import PanelPagination
from .privacy_serializers import PrivacyRequestSerializer

ALREADY_RESOLVED_CODE = "privacy_request_resolved"


class PrivacyRequestViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """``/api/platform/privacy-requests/``.

    - ``?state=pending`` (default): las que esperan decisión, **la más vieja
      primero**. Con un plazo único para todas, ese orden es exactamente
      "fuera de plazo primero, después por antigüedad" (escenario 7), sin
      necesidad de ordenar por una anotación.
    - ``?state=resolved``: el registro de cumplimiento (escenario 8), la
      decisión más reciente primero.
    - ``?municipality=<id>``: acota a una municipalidad.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PrivacyRequestSerializer
    pagination_class = PanelPagination

    def get_queryset(self):
        queryset = ReportComplaint.objects.for_platform_review().select_related(
            "report__municipality",
            "resolution_evidence",
            "reporter",
            "resolved_by",
        )
        if self.action == "list":
            if self.request.query_params.get("state") == "resolved":
                queryset = queryset.exclude(
                    status=ReportComplaint.Status.PENDIENTE,
                ).order_by("-resolved_at", "-pk")
            else:
                queryset = queryset.filter(
                    status=ReportComplaint.Status.PENDIENTE,
                ).order_by("created_at", "pk")
            municipality = self.request.query_params.get("municipality", "")
            if municipality.isdigit():
                queryset = queryset.filter(report__municipality_id=int(municipality))
        return queryset

    @action(detail=True, methods=["post"], url_path="remove-image")
    def remove_image(self, request, pk=None):
        """Elimina físicamente la imagen denunciada (escenarios 5 y 11)."""
        return self._resolve(remove_image)

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        """La imagen no expone ningún dato personal (escenario 6)."""
        return self._resolve(dismiss)

    def _resolve(self, decide):
        complaint = self.get_object()
        try:
            complaint = decide(complaint, admin=self.request.user)
        except ComplaintAlreadyResolvedError as error:
            return Response(
                {"code": ALREADY_RESOLVED_CODE, "detail": str(error)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(self.get_serializer(complaint).data)
