"""Bandeja de solicitudes por dato personal (US-043).

US-043 la pensó solo para el administrador (escenario 10). Por decisión del
usuario del 21/10 también la atiende el agente municipal, con las solicitudes
de su municipalidad: las ve y las resuelve. Otra municipalidad no existe para
él (``404``), igual que en el resto del panel. El administrador ve todas.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.privacy import ComplaintAlreadyResolvedError
from urbancheck.reports.privacy import dismiss
from urbancheck.reports.privacy import remove_image
from urbancheck.users.api.permissions import IsPanelUser

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

    serializer_class = PrivacyRequestSerializer

    #: Los dos roles del panel ven y resuelven (decisión del usuario del 21/10,
    #: contraria al escenario 10 de US-043); el agente, solo lo de su
    #: municipalidad, que acota ``get_queryset``.
    permission_classes = [IsAuthenticated, IsPanelUser]
    pagination_class = PanelPagination

    # Solo para que el esquema OpenAPI tipe el id: lo genera sin usuario.
    queryset = ReportComplaint.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ReportComplaint.objects.none()
        queryset = ReportComplaint.objects.for_platform_review().select_related(
            "report__municipality",
            "resolution_evidence",
            "reporter",
            "resolved_by",
        )
        user = self.request.user
        if not user.sees_every_municipality:
            # El agente, solo las de su jurisdicción: otra municipalidad no
            # existe para él (404), igual que en el resto del panel.
            queryset = queryset.filter(report__in=Report.objects.for_user(user))
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
