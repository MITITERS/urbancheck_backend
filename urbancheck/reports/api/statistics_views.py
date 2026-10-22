"""Sección de estadísticas del panel (US-023 y US-050).

Dos puertas a la misma respuesta:

- ``GET /api/panel/statistics/``: el agente, acotado a su municipalidad por
  ``for_user``. Cualquier parámetro de municipio que mande el cliente se ignora
  (escenario 8): el queryset no lo lee.
- ``GET /api/municipalities/{id}/statistics/``: el administrador, desde la ficha
  de una municipalidad (escenario 9). Vive en ``MunicipalityViewSet``.

Ciudadano, validador y operario reciben ``403`` (escenario 10).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from urbancheck.reports.models import Report
from urbancheck.reports.statistics import Period
from urbancheck.reports.statistics import PeriodError
from urbancheck.reports.statistics import build_statistics
from urbancheck.reports.statistics import resolve_window
from urbancheck.users.api.permissions import IsMunicipalAgent


class StatisticsQuerySerializer(serializers.Serializer):
    period = serializers.ChoiceField(
        choices=Period.CHOICES,
        required=False,
        default=Period.DEFAULT,
    )
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)


class _PeriodSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=Period.CHOICES)
    start = serializers.DateField()
    end = serializers.DateField()


class _BucketSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField(allow_null=True)


class _AverageSerializer(serializers.Serializer):
    """Un tiempo promedio con su tamaño de muestra. Nulo si no hay casos."""

    avg_seconds = serializers.FloatField(allow_null=True)
    sample_size = serializers.IntegerField()


class _ValidationSerializer(serializers.Serializer):
    overall = _AverageSerializer()
    field = _AverageSerializer()
    collective = _AverageSerializer()


class _OpenSerializer(serializers.Serializer):
    status = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    oldest_since = serializers.DateTimeField(allow_null=True)
    oldest_age_seconds = serializers.FloatField(allow_null=True)


class _AppealedClosuresSerializer(serializers.Serializer):
    closures = serializers.IntegerField()
    appealed = serializers.IntegerField()
    percentage = serializers.FloatField(allow_null=True)
    alert_threshold = serializers.IntegerField()
    above_threshold = serializers.BooleanField()


class _CancellationsSerializer(serializers.Serializer):
    field_rejection = serializers.IntegerField()
    moderation = serializers.IntegerField()
    municipal = serializers.IntegerField()


class _IndicatorsSerializer(serializers.Serializer):
    validation = _ValidationSerializer()
    assignment = _AverageSerializer()
    resolution = _AverageSerializer()
    open = _OpenSerializer(many=True)
    appealed_closures = _AppealedClosuresSerializer()
    cancellations = _CancellationsSerializer()
    archived_by_inactivity = serializers.IntegerField()


class StatisticsSerializer(serializers.Serializer):
    """La forma de la respuesta, para el esquema OpenAPI."""

    period = _PeriodSerializer()
    total = serializers.IntegerField()
    by_category = _BucketSerializer(many=True)
    by_status = _BucketSerializer(many=True)
    # Los indicadores de gestión de US-050, sobre el mismo período.
    indicators = _IndicatorsSerializer()


STATISTICS_PARAMETERS = [
    OpenApiParameter("period", str, enum=list(Period.CHOICES)),
    OpenApiParameter("start", str, description="aaaa-mm-dd, con period=custom"),
    OpenApiParameter("end", str, description="aaaa-mm-dd, con period=custom"),
]


def statistics_response(request, reports) -> Response:
    """Valida el período y arma la respuesta sobre ``reports``, ya acotado."""
    query = StatisticsQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    try:
        window = resolve_window(
            query.validated_data["period"],
            query.validated_data.get("start"),
            query.validated_data.get("end"),
        )
    except PeriodError as error:
        raise ValidationError({error.field: [error.message]}) from error
    return Response(StatisticsSerializer(build_statistics(reports, window)).data)


class PanelStatisticsView(APIView):
    permission_classes = [IsAuthenticated, IsMunicipalAgent]

    @extend_schema(parameters=STATISTICS_PARAMETERS, responses=StatisticsSerializer)
    def get(self, request):
        return statistics_response(request, Report.objects.for_user(request.user))
