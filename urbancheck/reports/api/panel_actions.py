"""Acciones de cambio de estado del panel municipal (US-013).

Un endpoint por transición y no un ``PATCH`` genérico de estado: los permisos y
los campos requeridos difieren por transición, y con un campo libre el cliente
podría pedir cualquier estado.

La lógica de qué transición es válida no está acá: vive en la máquina de estados
(``state_machine.py``) y la ejecuta ``services.apply_transition``.
"""

from rest_framework.decorators import action
from rest_framework.response import Response

from urbancheck.reports.services import TransitionError
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import Actor

from .transition_responses import transition_error_response


class ReportTransitionActionsMixin:
    """Las cinco acciones del agente municipal sobre un reporte.

    Cada una delega en la misma función de dominio; lo único que cambia es el
    nombre de la operación y, en cancelar, el motivo obligatorio.
    """

    def _run_transition(self, request, operation: str):
        report = self.get_object()
        try:
            apply_transition(
                report,
                operation,
                actor=Actor.MUNICIPAL_AGENT,
                changed_by=request.user,
                reason=request.data.get("reason", ""),
            )
        except TransitionError as error:
            return transition_error_response(error)

        report = self.get_queryset().get(pk=report.pk)
        serializer = self.get_detail_serializer(report, request)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Reportado → En proceso."""
        return self._run_transition(request, "procesar")

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """En proceso → Resuelto. Estado final."""
        return self._run_transition(request, "resolver")

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
