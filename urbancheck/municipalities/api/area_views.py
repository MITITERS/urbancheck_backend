"""API de gestión de áreas operativas municipales (US-039).

Vive en el panel y se acota por jurisdicción con el mismo mixin que el resto:
un agente ve, edita y desactiva únicamente las áreas de su municipalidad, y
pedir una ajena por id responde ``404``.
"""

from django.db.models import Count
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from urbancheck.municipalities.models import OperationalArea
from urbancheck.reports.api.mixins import JurisdictionScopedMixin
from urbancheck.users.api.permissions import IsPanelUser

from .area_serializers import OperationalAreaSerializer

NO_HARD_DELETE_MESSAGE = (
    "Un área operativa no se elimina: se desactiva. Los reportes que ya tiene "
    "asignados conservan el vínculo para no perder su trazabilidad."
)

# Filtro del listado: ``?state=active|inactive``. Mismo contrato que el de las
# cuentas de trabajo del panel, para que las dos tablas se filtren igual.
STATE_PARAM = "state"
STATE_ACTIVE = "active"
STATE_INACTIVE = "inactive"


class OperationalAreaViewSet(JurisdictionScopedMixin, ModelViewSet):
    """Alta, edición, listado y baja lógica de las áreas de una municipalidad.

    El mixin de jurisdicción va primero en el MRO a propósito: lo último que se
    aplica sobre el queryset es el filtro por municipalidad.

    **No hay borrado físico.** ``destroy`` existe solo para explicar por qué:
    borrar un área con reportes asignados perdería la constancia de qué
    dependencia se hizo cargo de cada reclamo.
    """

    permission_classes = [IsAuthenticated, IsPanelUser]
    serializer_class = OperationalAreaSerializer
    # Sin paginado: una municipalidad tiene un puñado de dependencias, y el
    # desplegable de asignación de US-028 las necesita todas de una.
    pagination_class = None
    queryset = (
        OperationalArea.objects.select_related("municipality")
        .annotate(
            report_count=Count("reports", distinct=True),
            operator_count=Count("operators", distinct=True),
        )
        .order_by("name")
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        # Solo en el listado: activar y desactivar tienen que poder alcanzar al
        # área esté del lado que esté, o reactivar desde el archivado
        # respondería 404.
        if self.action == "list":
            queryset = self._filter_by_state(queryset)
        return queryset

    def _filter_by_state(self, queryset):
        """Acota por ``?state=``. Un valor desconocido no filtra ni rompe.

        Sin el parámetro devuelve las dos, que es lo que muestra el listado de
        gestión. El desplegable de asignación de US-028 pide ``active``.
        """
        state = self.request.query_params.get(STATE_PARAM)
        if state == STATE_ACTIVE:
            return queryset.filter(is_active=True)
        if state == STATE_INACTIVE:
            return queryset.filter(is_active=False)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """No se borra: se desactiva.

        Se responde ``405`` y no ``403``: el método no existe para nadie, ni
        siquiera para el administrador de la plataforma. El objeto se busca
        igual antes de contestar para que un área de otra jurisdicción siga
        respondiendo ``404``, que es lo que dice US-034.
        """
        self.get_object()
        return Response(
            {"detail": NO_HARD_DELETE_MESSAGE},
            status=http_status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Baja lógica: deja de ofrecerse para asignar reportes nuevos.

        Los reportes ya asignados conservan el vínculo y el área sigue visible
        en sus historiales.
        """
        return self._set_active(request, active=False)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Vuelve a ofrecerse en el desplegable de asignación."""
        return self._set_active(request, active=True)

    def _set_active(self, request, *, active: bool) -> Response:
        area = self.get_object()
        area.is_active = active
        area.save(update_fields=["is_active", "updated_at"])
        area = self.get_queryset().get(pk=area.pk)
        return Response(self.get_serializer(area).data)
