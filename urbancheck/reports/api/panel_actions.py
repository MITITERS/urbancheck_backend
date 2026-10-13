"""Acciones de cambio de estado del panel municipal (US-013).

Un endpoint por transición y no un ``PATCH`` genérico de estado: los permisos y
los campos requeridos difieren por transición, y con un campo libre el cliente
podría pedir cualquier estado.

La lógica de qué transición es válida no está acá: vive en la máquina de estados
(``state_machine.py``) y la ejecuta ``services.apply_transition``.
"""

from rest_framework import serializers
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.response import Response

from urbancheck.municipalities.models import OperationalArea
from urbancheck.notifications.services import notify_official_response
from urbancheck.reports.models import OfficialResponse
from urbancheck.reports.services import TransitionError
from urbancheck.reports.services import apply_transition
from urbancheck.reports.services import reassign_area
from urbancheck.reports.state_machine import OFFICIAL_RESPONSE_STATUSES
from urbancheck.reports.state_machine import Actor

from .serializers import OfficialResponseCreateSerializer
from .transition_responses import transition_error_response

AREA_REQUIRED_MESSAGE = "Elegí el área operativa que se va a hacer cargo."
AREA_FOREIGN_MESSAGE = "El área operativa pertenece a otra municipalidad."
AREA_INACTIVE_MESSAGE = (
    "El área operativa está desactivada y no puede recibir reportes nuevos."
)
RESPONSE_NOT_ALLOWED_MESSAGE = (
    "El municipio no publica respuestas oficiales sobre un reporte en este "
    "estado."
)


class AreaAssignmentSerializer(serializers.Serializer):
    """El área que recibe el reporte, validada contra su jurisdicción (US-028).

    El área llega del cliente, así que las tres cosas que pueden estar mal se
    responden como error **de campo** y no como ``404`` del reporte: el reporte
    existe y es suyo, lo que no sirve es el área que eligió.

    El queryset arranca sin acotar y la jurisdicción se comprueba después, a
    propósito: acotarlo haría que un área de otro municipio dijera "no existe"
    en lugar de decir de quién es. La comprobación se hace contra la
    municipalidad **del reporte**, que es exactamente el conjunto que
    ``JurisdictionScopedMixin`` ya autorizó al entregar ese reporte.
    """

    area_id = serializers.PrimaryKeyRelatedField(
        queryset=OperationalArea.objects.all(),
        source="area",
        error_messages={
            "required": AREA_REQUIRED_MESSAGE,
            "null": AREA_REQUIRED_MESSAGE,
        },
    )

    def validate_area_id(self, area: OperationalArea) -> OperationalArea:
        report = self.context["report"]
        if area.municipality_id != report.municipality_id:
            raise serializers.ValidationError(AREA_FOREIGN_MESSAGE)
        if not area.is_active:
            raise serializers.ValidationError(AREA_INACTIVE_MESSAGE)
        return area


class ReportTransitionActionsMixin:
    """Las cinco acciones del agente municipal sobre un reporte.

    Cada una delega en la misma función de dominio; lo único que cambia es el
    nombre de la operación y, en cancelar, el motivo obligatorio.
    """

    def _run_transition(self, request, operation: str, *, operational_area=None):
        report = self.get_object()
        try:
            apply_transition(
                report,
                operation,
                actor=Actor.MUNICIPAL_AGENT,
                changed_by=request.user,
                reason=request.data.get("reason", ""),
                operational_area=operational_area,
            )
        except TransitionError as error:
            return transition_error_response(error)

        return self._detail_response(report, request)

    def _detail_response(self, report, request) -> Response:
        """Relee el reporte por el queryset anotado y lo devuelve entero.

        Se relee y no se serializa la instancia en memoria porque el detalle
        lleva anotaciones y relaciones prefetcheadas que la instancia no tiene.
        """
        report = self.get_queryset().get(pk=report.pk)
        return Response(self.get_detail_serializer(report, request).data)

    def _area_from_request(self, request, report) -> OperationalArea:
        serializer = AreaAssignmentSerializer(
            data=request.data,
            context={"report": report, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["area"]

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Reportado → En proceso, asignando el área responsable (US-028).

        El área es obligatoria: asignarla **es** procesar el reporte, no un paso
        aparte. La exigencia vive en la máquina de estados —``requires_area``—,
        así que ningún otro camino puede dejar un reporte En proceso sin
        responsable operativo.
        """
        report = self.get_object()
        area = self._area_from_request(request, report)
        return self._run_transition(request, "procesar", operational_area=area)

    @action(detail=True, methods=["post"], url_path="assign-area")
    def assign_area(self, request, pk=None):
        """Reasigna el área de un reporte que **ya** está En proceso (US-028).

        Endpoint aparte y no una transición: el reporte no cambia de estado. Por
        eso tampoco puede usarse para desasignar —el área es obligatoria— ni
        para hacer entrar un reporte a gestión, que es lo que hace ``process``.
        """
        report = self.get_object()
        area = self._area_from_request(request, report)
        try:
            reassign_area(report, area, assigned_by=request.user)
        except TransitionError as error:
            return transition_error_response(error)
        return self._detail_response(report, request)

    @action(detail=True, methods=["post"], url_path="official-responses")
    def official_responses(self, request, pk=None):
        """Publica una respuesta oficial en el hilo del reporte (US-024).

        Solo publica: no hay actualización ni borrado, y la inmutabilidad del
        hilo se sostiene en esa ausencia. Una corrección se publica como una
        respuesta nueva.

        Qué estados la habilitan lo decide ``OFFICIAL_RESPONSE_STATUSES``, en la
        máquina de estados, y no una lista escrita acá.
        """
        report = self.get_object()
        if report.status not in OFFICIAL_RESPONSE_STATUSES:
            return Response(
                {
                    "detail": RESPONSE_NOT_ALLOWED_MESSAGE,
                    "current_status": report.status,
                },
                status=http_status.HTTP_409_CONFLICT,
            )

        serializer = OfficialResponseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = OfficialResponse.objects.create(
            report=report,
            author=request.user,
            # Derivada del reporte y nunca del cliente. Coincide con la del
            # agente por construcción: la capa de jurisdicción no le entrega
            # reportes de otro municipio.
            municipality=report.municipality,
            text=serializer.validated_data["text"],
        )
        # El autor del reporte se entera de que el municipio le respondió
        # (US-011), igual que con un cambio de estado.
        notify_official_response(response)
        return self._detail_response(report, request)

    @action(detail=True, methods=["post"], url_path="confirm-resolution")
    def confirm_resolution(self, request, pk=None):
        """Resuelto pendiente de confirmación → Resuelto. Estado final.

        US-046 sacó del panel la transición directa ``resolver``: el agente ya no
        declara resuelto un trabajo que no ejecutó. Lo que sí puede es
        **confirmar** el cierre del operario sin esperar a que venza la ventana
        de objeción, cuando verificó la resolución por su cuenta (US-047,
        escenario 7). La transición queda registrada con su usuario, a
        diferencia de la confirmación automática.
        """
        return self._run_transition(request, "confirmar_resolucion_municipal")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """En proceso → Cancelado. Exige motivo. Estado final."""
        return self._run_transition(request, "cancelar")

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """En proceso → Archivado."""
        return self._run_transition(request, "archivar")

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        """Archivado → Reportado."""
        return self._run_transition(request, "reactivar")
