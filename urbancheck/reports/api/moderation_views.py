"""Moderación de contenido desde el panel (US-049).

Dos superficies con dos alcances distintos, a propósito:

- **La bandeja del agente** (``/api/panel/moderation/``) pasa por la capa de
  jurisdicción de US-034: un reporte de otra municipalidad no existe para él,
  así que resolverlo conociendo el id responde ``404`` (escenario 9).
- **Las apelaciones** (``/api/panel/moderation-appeals/``) las resuelven el
  administrador, que ve las de todas las municipalidades, y el agente, que ve
  solo las de la suya (decisión del usuario del 20/10; la historia las dejaba
  solo en manos de la plataforma). Una apelación de otro municipio no existe
  para el agente: ``404``.
- **La reversión de oficio** (``/api/platform/reports/...``) sigue siendo solo
  del administrador.
"""

from __future__ import annotations

from django.db.models import Count
from django.db.models import IntegerField
from django.db.models import Min
from django.db.models import OuterRef
from django.db.models import Prefetch
from django.db.models import Subquery
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.reports.models import ModerationDecision
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import on_privacy_hold
from urbancheck.reports.moderation import AppealAlreadyResolvedError
from urbancheck.reports.moderation import ModerationError
from urbancheck.reports.moderation import NotAppealableError
from urbancheck.reports.moderation import NothingToResolveError
from urbancheck.reports.moderation import discard_report
from urbancheck.reports.moderation import dismiss_complaints
from urbancheck.reports.moderation import resolve_moderation_appeal
from urbancheck.reports.moderation import revert_moderation
from urbancheck.reports.services import TransitionError
from urbancheck.users.api.permissions import IsMunicipalAgent
from urbancheck.users.api.permissions import IsPanelUser
from urbancheck.users.api.permissions import IsPlatformAdmin

from .mixins import JurisdictionScopedMixin
from .moderation_serializers import ModerationAppealSerializer
from .moderation_serializers import ModerationInboxEntrySerializer
from .moderation_serializers import ModerationReasonSerializer
from .moderation_serializers import ResolvedModerationSerializer
from .pagination import PanelPagination
from .panel_serializers import PanelReportDetailSerializer
from .transition_responses import transition_error_response

ALREADY_RESOLVED_CODE = "moderation_already_resolved"

#: Los motivos que modera el agente, para el filtro ``?reason=``.
CONTENT_REASONS = {
    reason
    for reason in ReportComplaint.Reason.values
    if reason not in ReportComplaint.PLATFORM_REASONS
}
NOT_DISCARDED_CODE = "moderation_not_discarded"


def _conflict(code: str, error: Exception) -> Response:
    return Response(
        {"code": code, "detail": str(error)},
        status=status.HTTP_409_CONFLICT,
    )


class ModerationViewSet(JurisdictionScopedMixin, ListModelMixin, GenericViewSet):
    """Bandeja de denuncias por contenido del agente municipal.

    - ``GET /``: un reporte por entrada, con sus denuncias pendientes, la
      denuncia más vieja primero (escenarios 1 y 2).
    - ``GET /count/``: cuántos reportes esperan decisión, para el contador de
      la navegación.
    - ``GET /resolved/``: las decisiones ya tomadas, la más reciente primero.
      Acepta el mismo ``?reason=``.
    - ``POST /{report_id}/discard/`` y ``/{report_id}/dismiss/``, con
      ``{"reason": ...}``.

    Resolver es solo del agente (US-049). El administrador de la plataforma
    puede **leer** la bandeja y su contador, de la municipalidad que eligió en el
    panel (``?municipality=<id>``), pero no descarta ni desestima. El resto de
    los roles recibe ``403`` (escenario 11).
    """

    #: Lo que el admin puede hacer acá: mirar.
    READ_ACTIONS = frozenset({"list", "count", "resolved"})

    def get_permissions(self):
        if self.action in self.READ_ACTIONS:
            return [IsAuthenticated(), IsPanelUser()]
        return [IsAuthenticated(), IsMunicipalAgent()]

    pagination_class = PanelPagination
    serializer_class = ModerationInboxEntrySerializer
    queryset = Report.objects.all()

    def get_queryset(self):
        # El mixin acota por jurisdicción sobre lo que devuelva ``super()``.
        queryset = super().get_queryset()
        if self.request.user.sees_every_municipality:
            municipality = self.request.query_params.get("municipality", "")
            if municipality.isdigit():
                queryset = queryset.filter(municipality_id=int(municipality))
        if self.action in {"list", "count"}:
            pending = ReportComplaint.objects.for_municipal_review().filter(
                status=ReportComplaint.Status.PENDIENTE,
            )
            # El filtro por tipo de la pantalla de denuncias: ``?reason=`` acota
            # a los reportes con denuncias pendientes de ese motivo, y las
            # denuncias que se listan a ese motivo.
            reason = self.request.query_params.get("reason", "")
            if reason in CONTENT_REASONS:
                pending = pending.filter(reason=reason)
            # La cantidad sale del mismo conjunto que se lista: con el filtro,
            # la tarjeta cuenta solo las de ese motivo.
            count = (
                pending.filter(report=OuterRef("pk"))
                .order_by()
                .values("report")
                .annotate(total=Count("pk"))
                .values("total")[:1]
            )
            oldest = (
                pending.filter(report=OuterRef("pk"))
                .order_by("created_at")
                .values("created_at")[:1]
            )
            queryset = (
                queryset.annotate(
                    pending_complaint_count=Coalesce(
                        Subquery(count, output_field=IntegerField()),
                        0,
                    ),
                    oldest_complaint_at=Subquery(oldest),
                    privacy_hold=on_privacy_hold(),
                )
                .filter(pending_complaint_count__gt=0)
                .select_related("author")
                .prefetch_related(
                    Prefetch(
                        "complaints",
                        queryset=pending.select_related("reporter"),
                        to_attr="pending_content_complaints",
                    ),
                )
                .order_by("oldest_complaint_at", "pk")
            )
        return queryset

    @extend_schema(
        responses=inline_serializer(
            "ModerationCount",
            {"pending": serializers.IntegerField()},
        ),
    )
    @action(detail=False, methods=["get"])
    def count(self, request):
        return Response({"pending": self.get_queryset().count()})

    @extend_schema(responses=ResolvedModerationSerializer(many=True))
    @action(detail=False, methods=["get"])
    def resolved(self, request):
        """El registro de lo resuelto, con el mismo alcance que la bandeja."""
        decisions = (
            ModerationDecision.objects.filter(report__in=self.get_queryset())
            .annotate(received_at=Min("complaints__created_at"))
            .select_related(
                "decided_by",
                "reverted_by",
                "report__municipality",
            )
            .prefetch_related(
                Prefetch(
                    "complaints",
                    queryset=ReportComplaint.objects.select_related("reporter"),
                ),
            )
            .order_by("-created_at", "-pk")
        )
        reason = request.query_params.get("reason", "")
        if reason in CONTENT_REASONS:
            decisions = decisions.filter(
                pk__in=ReportComplaint.objects.filter(reason=reason).values(
                    "moderation_decision",
                ),
            )
        page = self.paginate_queryset(decisions)
        serializer = ResolvedModerationSerializer(
            page,
            many=True,
            context=self.get_serializer_context(),
        )
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=ModerationReasonSerializer,
        responses=PanelReportDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def discard(self, request, pk=None):
        """El reporte es falso, inexistente u ofensivo: pasa a Cancelado."""
        return self._decide(discard_report)

    @extend_schema(
        request=ModerationReasonSerializer,
        responses=PanelReportDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        """El reporte es legítimo: las denuncias se desestiman."""
        return self._decide(dismiss_complaints)

    def _decide(self, decide):
        report = self.get_object()
        serializer = ModerationReasonSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        try:
            decide(
                report,
                agent=self.request.user,
                reason=serializer.validated_data["reason"],
            )
        except NothingToResolveError as error:
            return _conflict(ALREADY_RESOLVED_CODE, error)
        except TransitionError as error:
            return transition_error_response(error)
        report.refresh_from_db()
        return Response(
            PanelReportDetailSerializer(report, context={"request": self.request}).data,
        )


class ModerationAppealViewSet(ListModelMixin, GenericViewSet):
    """``/api/panel/moderation-appeals/``: las apelaciones contra descartes.

    - ``?state=pending`` (default): las que esperan decisión, la más vieja
      primero.
    - ``?state=resolved``: las ya resueltas, la más reciente primero.
    - ``?municipality=<id>``: solo para el administrador, acota a una.
    - ``POST /{id}/accept/`` y ``/{id}/reject/``, con ``{"reason": ...}``.

    Acotada por jurisdicción con la misma regla que el resto del panel: se
    filtra por los reportes que ``for_user`` le deja ver al usuario, y el
    administrador —``sees_every_municipality``— las ve todas.
    """

    permission_classes = [IsAuthenticated, IsPanelUser]
    pagination_class = PanelPagination
    serializer_class = ModerationAppealSerializer
    # Solo para que el esquema OpenAPI tipe el id: lo genera sin usuario.
    queryset = ResolutionAppeal.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ResolutionAppeal.objects.none()
        queryset = ResolutionAppeal.objects.filter(
            kind=ResolutionAppeal.Kind.MODERACION,
        ).select_related(
            "author",
            "resolved_by",
            "report__municipality",
            "moderation_decision__decided_by",
        )
        user = self.request.user
        if not user.sees_every_municipality:
            queryset = queryset.filter(report__in=Report.objects.for_user(user))
        else:
            municipality = self.request.query_params.get("municipality", "")
            if municipality.isdigit():
                queryset = queryset.filter(report__municipality_id=int(municipality))
        if self.action == "list":
            if self.request.query_params.get("state") == "resolved":
                return queryset.exclude(
                    status=ResolutionAppeal.Status.PENDIENTE,
                ).order_by("-resolved_at", "-pk")
            return queryset.filter(
                status=ResolutionAppeal.Status.PENDIENTE,
            ).order_by("created_at", "pk")
        return queryset

    @extend_schema(
        request=ModerationReasonSerializer,
        responses=ModerationAppealSerializer,
    )
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        """Hace lugar: el reporte vuelve al estado previo al descarte."""
        return self._resolve(accept=True)

    @extend_schema(
        request=ModerationReasonSerializer,
        responses=ModerationAppealSerializer,
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """No hace lugar: el reporte queda Cancelado, sin segunda apelación."""
        return self._resolve(accept=False)

    def _resolve(self, *, accept: bool):
        appeal = self.get_object()
        serializer = ModerationReasonSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        try:
            appeal = resolve_moderation_appeal(
                appeal,
                reviewer=self.request.user,
                accept=accept,
                reason=serializer.validated_data["reason"],
            )
        except AppealAlreadyResolvedError as error:
            return _conflict(ALREADY_RESOLVED_CODE, error)
        except ModerationError as error:
            return _conflict(NOT_DISCARDED_CODE, error)
        except TransitionError as error:
            return transition_error_response(error)
        return Response(self.get_serializer(appeal).data)


class PlatformReportModerationViewSet(GenericViewSet):
    """``/api/platform/reports/{id}/revert-moderation/`` (escenario 8).

    La reversión de oficio: el administrador detecta un descarte injustificado
    sin que medie apelación. Si había una apelación pendiente, se resuelve por
    su propio endpoint; esta vía no la deja colgada, la marca aceptada.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = Report.objects.all()

    @extend_schema(
        request=ModerationReasonSerializer,
        responses=PanelReportDetailSerializer,
    )
    @action(detail=True, methods=["post"], url_path="revert-moderation")
    def revert_moderation(self, request, pk=None):
        report = self.get_object()
        serializer = ModerationReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]
        pending_appeal = ResolutionAppeal.objects.filter(
            report=report,
            kind=ResolutionAppeal.Kind.MODERACION,
            status=ResolutionAppeal.Status.PENDIENTE,
        ).first()
        try:
            if pending_appeal is not None:
                resolve_moderation_appeal(
                    pending_appeal,
                    reviewer=request.user,
                    accept=True,
                    reason=reason,
                )
            else:
                revert_moderation(report, reviewer=request.user, reason=reason)
        except (NotAppealableError, AppealAlreadyResolvedError) as error:
            return _conflict(NOT_DISCARDED_CODE, error)
        except TransitionError as error:
            return transition_error_response(error)
        report.refresh_from_db()
        return Response(
            PanelReportDetailSerializer(report, context={"request": request}).data,
        )
