"""Máquina de estados del reporte, declarada una sola vez (US-013).

Todo cambio de estado del sistema —el panel municipal y la validación en
terreno de la app móvil— consulta esta tabla. Si se implementara dos veces, las
dos copias divergirían: es exactamente el bug que esta estructura evita.

La ejecución de una transición vive en ``services.transition_report``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import Report


class Actor(StrEnum):
    """Quién tiene permitido ejecutar una transición."""

    MUNICIPAL_AGENT = "agente_municipal"
    VALIDATOR = "validador"


@dataclass(frozen=True)
class Transition:
    """Una transición válida de la máquina de estados."""

    #: Nombre de la operación de dominio, tal como la nombran las historias.
    operation: str
    source: str
    target: str
    actor: Actor
    #: Si es True, la transición no se ejecuta sin un motivo escrito.
    requires_reason: bool = False


TRANSITIONS: tuple[Transition, ...] = (
    # Validación en terreno (US-036), ejecutada desde la app móvil.
    Transition(
        operation="validar",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.REPORTADO,
        actor=Actor.VALIDATOR,
    ),
    Transition(
        operation="rechazar",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.CANCELADO,
        actor=Actor.VALIDATOR,
        requires_reason=True,
    ),
    # Gestión municipal (US-013), ejecutada desde el panel web.
    Transition(
        operation="procesar",
        source=Report.Status.REPORTADO,
        target=Report.Status.EN_PROCESO,
        actor=Actor.MUNICIPAL_AGENT,
    ),
    Transition(
        operation="resolver",
        source=Report.Status.EN_PROCESO,
        target=Report.Status.RESUELTO,
        actor=Actor.MUNICIPAL_AGENT,
    ),
    Transition(
        operation="cancelar",
        source=Report.Status.EN_PROCESO,
        target=Report.Status.CANCELADO,
        actor=Actor.MUNICIPAL_AGENT,
        requires_reason=True,
    ),
    Transition(
        operation="archivar",
        source=Report.Status.EN_PROCESO,
        target=Report.Status.ARCHIVADO,
        actor=Actor.MUNICIPAL_AGENT,
    ),
    Transition(
        operation="reactivar",
        source=Report.Status.ARCHIVADO,
        target=Report.Status.REPORTADO,
        actor=Actor.MUNICIPAL_AGENT,
    ),
)

#: Qué decidió el validador, según a dónde mandó el reporte desde
#: *Pendiente de validación*. Son las dos únicas transiciones que ejecuta un
#: validador, y las dos salen del mismo estado: por eso alcanza con el destino
#: para nombrar la decisión.
#:
#: Se identifica por la transición completa y no por el estado de llegada.
#: ``reactivar`` también deja el reporte en *Reportado* y ``cancelar`` también
#: lo deja en *Cancelado*, pero las dos las ejecuta un agente desde el panel:
#: mirar solo el destino haría pasar a ese agente por validador.
VALIDATOR_DECISIONS: dict[str, str] = {
    Report.Status.REPORTADO: "validado",
    Report.Status.CANCELADO: "rechazado",
}

#: Estados sin transiciones de salida.
FINAL_STATUSES = frozenset({Report.Status.RESUELTO, Report.Status.CANCELADO})

_BY_OPERATION = {transition.operation: transition for transition in TRANSITIONS}


def get_transition(operation: str) -> Transition | None:
    return _BY_OPERATION.get(operation)


def transitions_from(status: str, actor: Actor | None = None) -> tuple[Transition, ...]:
    """Transiciones disponibles desde ``status``.

    El panel las consume para renderizar solo las acciones posibles, en lugar de
    dibujar cinco botones y deshabilitar cuatro.
    """
    return tuple(
        transition
        for transition in TRANSITIONS
        if transition.source == status and (actor is None or transition.actor == actor)
    )


def is_valid(source: str, target: str, actor: Actor | None = None) -> bool:
    return any(
        transition.source == source
        and transition.target == target
        and (actor is None or transition.actor == actor)
        for transition in TRANSITIONS
    )
