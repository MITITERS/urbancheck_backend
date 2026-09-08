"""Máquina de estados del reporte, declarada una sola vez (US-013).

Todo cambio de estado del sistema —el panel municipal y la validación en
terreno de la app móvil— consulta esta tabla. Si se implementara dos veces, las
dos copias divergirían: es exactamente el bug que esta estructura evita.

La ejecución de una transición vive en ``services.transition_report``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .models import Report


class Actor(StrEnum):
    """Quién tiene permitido ejecutar una transición."""

    MUNICIPAL_AGENT = "agente_municipal"
    VALIDATOR = "validador"
    #: El operario que ejecuta el trabajo en la vía pública (US-046).
    OPERATOR = "operario"
    #: El ciudadano autor del reporte. Hoy solo apela un cierre (US-048).
    CITIZEN = "ciudadano"
    #: La verificación periódica de US-031 y US-047, y la validación colectiva
    #: de US-040. No es un usuario: las transiciones que ejecuta quedan
    #: asentadas con ``changed_by`` nulo, que es como el historial dice "esto no
    #: lo decidió una persona".
    SYSTEM = "sistema"


class Origin(StrEnum):
    """De dónde salió una transición, más allá de a qué estado llegó.

    Dos transiciones pueden producir el mismo estado y **certificar cosas
    distintas**: un reporte llega a *Reportado* porque un validador fue al lugar
    (US-036) o porque diez vecinos lo confirmaron (US-040), y el panel tiene que
    poder distinguirlo. Lo mismo con *Resuelto*, al que se llega por silencio del
    autor o por decisión del agente.

    Es el discriminador que consume US-038. Se declara en la tabla de
    transiciones, no lo elige quien invoca: así una operación no puede quedar
    asentada con un origen que no le corresponde.
    """

    #: Lo decidió una persona ejerciendo su rol, por la vía normal.
    MANUAL = "manual"
    VALIDACION_TERRENO = "validacion_terreno"
    VALIDACION_COLECTIVA = "validacion_colectiva"
    CIERRE_OPERARIO = "cierre_operario"
    CONFIRMACION_AUTOMATICA = "confirmacion_automatica"
    APELACION_CIUDADANO = "apelacion_ciudadano"
    ARCHIVADO_INACTIVIDAD = "archivado_inactividad"


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
    #: Si es True, la transición no se ejecuta sin un área operativa (US-028).
    #: Es lo que garantiza que **no existe ningún camino a En proceso sin
    #: área**: la exigencia está en la tabla, no en el endpoint que la invoca.
    requires_area: bool = False
    #: De dónde salió la transición. Se escribe en el historial tal como está
    #: acá: quien invoca no lo elige.
    origin: Origin = Origin.MANUAL
    #: Condición sobre el **reporte**, más allá de su estado, que la transición
    #: exige para poder ejecutarse. Devuelve ``None`` si está habilitada, o el
    #: motivo del rechazo si no.
    #:
    #: Existe para que reglas como "una sola apelación por reporte" (US-048)
    #: vivan en la tabla y no en la vista: si estuvieran en la vista, un segundo
    #: endpoint que llamara a la misma transición se las saltearía.
    guard: Callable[[Report], str | None] | None = None


#: Cuántas veces puede el autor apelar el cierre de un mismo reporte (US-048).
#:
#: Una. El segundo cierre del operario es definitivo: sin este tope, un autor
#: insatisfecho y una cuadrilla pueden reabrir el mismo reporte indefinidamente
#: y *Resuelto* deja de ser alcanzable.
MAX_APPEALS_PER_REPORT = 1

APPEAL_LIMIT_MESSAGE = (
    "Ya apelaste el cierre de este reporte una vez. La resolución registrada "
    "es definitiva."
)


def _within_appeal_limit(report: Report) -> str | None:
    """Guarda de ``apelar``: el tope de apelaciones vive en la tabla."""
    if report.appeal_count >= MAX_APPEALS_PER_REPORT:
        return APPEAL_LIMIT_MESSAGE
    return None


TRANSITIONS: tuple[Transition, ...] = (
    # Validación en terreno (US-036), ejecutada desde la app móvil.
    Transition(
        operation="validar",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.REPORTADO,
        actor=Actor.VALIDATOR,
        origin=Origin.VALIDACION_TERRENO,
    ),
    Transition(
        operation="rechazar",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.CANCELADO,
        actor=Actor.VALIDATOR,
        requires_reason=True,
    ),
    # Gestión municipal (US-013), ejecutada desde el panel web.
    # US-028 redefinió esta transición: asignar el área **es** procesar el
    # reporte. No hay forma de pasar a En proceso sin área ni de asignar un área
    # sin pasar a En proceso, así que el área es un parámetro obligatorio de la
    # misma transición y no un camino nuevo.
    Transition(
        operation="procesar",
        source=Report.Status.REPORTADO,
        target=Report.Status.EN_PROCESO,
        actor=Actor.MUNICIPAL_AGENT,
        requires_area=True,
    ),
    # US-046 sacó la transición directa ``resolver`` del agente municipal: todo
    # camino hacia *Resuelto* pasa ahora por *Resuelto pendiente de
    # confirmación*. El agente sigue pudiendo cerrar el circuito, pero desde el
    # estado intermedio y como contraparte del operario, no en lugar de él.
    #
    # Cierre en terreno (US-046), ejecutado por el operario desde la app.
    Transition(
        operation="registrar_resolucion",
        source=Report.Status.EN_PROCESO,
        target=Report.Status.RESUELTO_PENDIENTE,
        actor=Actor.OPERATOR,
        origin=Origin.CIERRE_OPERARIO,
    ),
    # El segundo cierre, después de una apelación, es definitivo: no abre una
    # ventana de objeción nueva porque ya no queda apelación disponible
    # (US-047, escenario 6). Es una transición aparte y no un destino dinámico
    # para que la tabla siga diciendo la verdad completa de un vistazo.
    Transition(
        operation="registrar_resolucion_definitiva",
        source=Report.Status.EN_PROCESO,
        target=Report.Status.RESUELTO,
        actor=Actor.OPERATOR,
        origin=Origin.CIERRE_OPERARIO,
    ),
    # Confirmación del cierre (US-047). Dos caminos al mismo estado: el silencio
    # del autor al vencer el plazo, y la verificación anticipada del agente.
    Transition(
        operation="confirmar_resolucion",
        source=Report.Status.RESUELTO_PENDIENTE,
        target=Report.Status.RESUELTO,
        actor=Actor.SYSTEM,
        origin=Origin.CONFIRMACION_AUTOMATICA,
    ),
    Transition(
        operation="confirmar_resolucion_municipal",
        source=Report.Status.RESUELTO_PENDIENTE,
        target=Report.Status.RESUELTO,
        actor=Actor.MUNICIPAL_AGENT,
    ),
    # Apelación del ciudadano autor (US-048). Vuelve a *En proceso* y **no** a
    # *Reportado*: el trabajo mal ejecutado le corresponde a quien lo ejecutó,
    # así que el reporte conserva su área operativa.
    Transition(
        operation="apelar",
        source=Report.Status.RESUELTO_PENDIENTE,
        target=Report.Status.EN_PROCESO,
        actor=Actor.CITIZEN,
        requires_reason=True,
        origin=Origin.APELACION_CIUDADANO,
        guard=_within_appeal_limit,
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
    # Archivado automático por inactividad (US-031), ejecutado por la
    # verificación periódica. Va en esta tabla y no en el comando que la corre
    # para que sea una transición como las demás: deja asiento en el historial y
    # dispara el mismo evento del que cuelgan las notificaciones.
    # Validación colectiva por umbral de likes (US-040). Es el **segundo**
    # camino hacia *Reportado*: no exige presencia física, se apoya en la
    # cantidad de confirmaciones distintas. Llega al mismo estado que la
    # validación en terreno y certifica otra cosa, y por eso lleva otro origen.
    Transition(
        operation="validar_colectivamente",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.REPORTADO,
        actor=Actor.SYSTEM,
        origin=Origin.VALIDACION_COLECTIVA,
    ),
    Transition(
        operation="archivar_por_inactividad",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.ARCHIVADO,
        actor=Actor.SYSTEM,
        origin=Origin.ARCHIVADO_INACTIVIDAD,
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
#: mirar solo el destino haría pasar a ese agente por validador. Desde US-040
#: hay una razón más: la validación colectiva también deja el reporte en
#: *Reportado* y ahí no hubo ningún validador.
VALIDATOR_DECISIONS: dict[str, str] = {
    Report.Status.REPORTADO: "validado",
    Report.Status.CANCELADO: "rechazado",
}

#: Estados sin transiciones de salida.
FINAL_STATUSES = frozenset({Report.Status.RESUELTO, Report.Status.CANCELADO})

#: Estados en los que el municipio puede publicar una respuesta oficial
#: (US-024). Vive acá, junto a la tabla de transiciones, y no dentro de la
#: vista: es una regla sobre el estado del reporte, y las reglas sobre el estado
#: se declaran en un solo archivo o terminan divergiendo.
#:
#: Son los estados de gestión activa. Antes de la validación el municipio no se
#: pronuncia institucionalmente sobre un reclamo que todavía nadie confirmó;
#: sobre uno cancelado o archivado ya no hay nada que comprometer; y una vez
#: confirmado el cierre la comunicación pasa a ser la evidencia de resolución de
#: US-046, que publica el operario.
#:
#: *Resuelto pendiente de confirmación* sí está incluido —lo pide el escenario 1
#: de US-024—: mientras corre la ventana de objeción el caso sigue abierto, y es
#: justo cuando el municipio puede necesitar explicar el cierre.
OFFICIAL_RESPONSE_STATUSES = frozenset(
    {
        Report.Status.REPORTADO,
        Report.Status.EN_PROCESO,
        Report.Status.RESUELTO_PENDIENTE,
    },
)

#: Estado en el que un reporte puede reasignarse de área sin cambiar de estado
#: (US-028). La reasignación no es una transición —el reporte permanece En
#: proceso—, pero sí es una regla sobre el estado, así que se declara acá.
AREA_REASSIGNMENT_STATUS = Report.Status.EN_PROCESO

#: Estado desde el que un operario puede registrar la resolución (US-046).
RESOLUTION_STATUS = Report.Status.EN_PROCESO

#: Estado durante el cual corre la ventana de objeción del autor (US-047).
OBJECTION_STATUS = Report.Status.RESUELTO_PENDIENTE


def closing_operation(report: Report) -> str:
    """Qué transición de cierre le corresponde a ``report`` (US-046, US-047).

    El primer cierre abre la ventana de objeción del autor. El segundo —el que
    sigue a una apelación— es definitivo, porque el autor ya gastó la única
    apelación que tiene y no habría a quién darle una ventana nueva.

    Vive acá y no en la vista por lo mismo que la guarda de ``apelar``: es una
    regla sobre el reporte, y si la decidiera cada endpoint, dos endpoints
    terminarían decidiéndola distinto.
    """
    if report.appeal_count >= MAX_APPEALS_PER_REPORT:
        return "registrar_resolucion_definitiva"
    return "registrar_resolucion"

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
