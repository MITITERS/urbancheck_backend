"""Máquina de estados del reporte, declarada una sola vez (US-013).

Todo cambio de estado del sistema —el panel municipal y la validación en
terreno de la app móvil— consulta esta tabla. Si se implementara dos veces, las
dos copias divergirían: es exactamente el bug que esta estructura evita.

La ejecución de una transición vive en ``services.transition_report``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .models import Report

if TYPE_CHECKING:
    from collections.abc import Callable


class Actor(StrEnum):
    """Quién tiene permitido ejecutar una transición."""

    MUNICIPAL_AGENT = "agente_municipal"
    VALIDATOR = "validador"
    #: El operario que ejecuta el trabajo en la vía pública (US-046).
    OPERATOR = "operario"
    #: El ciudadano autor del reporte. Hoy solo apela un cierre (US-048).
    CITIZEN = "ciudadano"
    #: El administrador de la plataforma. Hoy solo revierte un descarte por
    #: moderación municipal (US-049): es el contrapeso de esa facultad, y por
    #: eso no la ejerce el mismo municipio que descartó.
    PLATFORM_ADMIN = "admin_plataforma"
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
    #: El agente descartó el reporte al resolver una denuncia por contenido
    #: (US-049). Llega a *Cancelado* igual que el rechazo del validador y que la
    #: cancelación del agente desde *En proceso*, y US-050 los cuenta aparte.
    MODERACION_MUNICIPAL = "moderacion_municipal"
    #: El administrador de la plataforma restituyó un reporte descartado por
    #: moderación, por apelación del autor o de oficio (US-049).
    REVERSION_MODERACION = "reversion_moderacion"


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
    #: Otros actores que también pueden ejecutarla, además de ``actor``. Hoy
    #: solo la restitución de un descarte, que resuelven el administrador y el
    #: agente de la jurisdicción (US-049, decisión del usuario).
    extra_actors: frozenset[Actor] = frozenset()

    def allows(self, actor: Actor) -> bool:
        return actor == self.actor or actor in self.extra_actors


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


#: Estados desde los que el agente puede descartar un reporte por moderación
#: (US-049): todos los que el vecino ve publicados. Un reporte cancelado o
#: archivado ya está fuera del feed y del mapa, y no hay nada que descartar.
MODERATION_SOURCES: tuple[str, ...] = (
    Report.Status.PENDIENTE_VALIDACION,
    Report.Status.REPORTADO,
    Report.Status.EN_PROCESO,
    Report.Status.RESUELTO_PENDIENTE,
    Report.Status.RESUELTO,
)

NO_PENDING_COMPLAINTS_MESSAGE = (
    "Este reporte no tiene denuncias por contenido pendientes de resolución."
)
NO_DISCARD_MESSAGE = "Este reporte no fue descartado por moderación municipal."
WRONG_RESTORE_TARGET_MESSAGE = (
    "El reporte se restituye al estado que tenía antes del descarte, no a otro."
)
RESTORE_WITHOUT_AREA_MESSAGE = (
    "El reporte no tiene un área operativa responsable y no puede volver a "
    "En proceso."
)


def _has_pending_content_complaints(report: Report) -> str | None:
    """Guarda del descarte: se descarta resolviendo denuncias, no a voluntad.

    Sin esto, el descarte sería una cancelación libre desde cualquier estado
    —incluso Resuelto— con otro nombre, y el agente tendría un camino para
    sacar del feed un reclamo incómodo que nadie denunció.
    """
    if report.complaints.for_municipal_review().filter(
        status="pendiente",
    ).exists():
        return None
    return NO_PENDING_COMPLAINTS_MESSAGE


def _restores_status(target: str) -> Callable[[Report], str | None]:
    """Guarda de ``restituir_a_<estado>``: vuelve al estado previo al descarte.

    El estado anterior se persiste al descartar (``ModerationDecision``) y no se
    asume: un reporte puede haber sido descartado estando En proceso o Resuelto,
    y devolverlo siempre a Reportado le borraría la gestión que tenía.
    """

    def guard(report: Report) -> str | None:
        decision = report.active_discard()
        if decision is None:
            return NO_DISCARD_MESSAGE
        if decision.previous_status != target:
            return WRONG_RESTORE_TARGET_MESSAGE
        # Ningún camino a En proceso sin área (US-028). Cancelar no la borra,
        # así que un reporte descartado estando En proceso la conserva; esto
        # lo garantiza en vez de suponerlo.
        if target == Report.Status.EN_PROCESO and report.operational_area_id is None:
            return RESTORE_WITHOUT_AREA_MESSAGE
        return None

    return guard


def restore_operation(status: str) -> str:
    """La operación que devuelve un reporte descartado a ``status`` (US-049)."""
    return f"restituir_a_{status}"


TRANSITIONS: tuple[Transition, ...] = (
    # Validación en terreno (US-036), ejecutada desde la app móvil.
    Transition(
        operation="validar",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.REPORTADO,
        actor=Actor.VALIDATOR,
        origin=Origin.VALIDACION_TERRENO,
    ),
    # El rechazo también es una decisión en terreno, y lleva el mismo origen
    # que la validación. Hasta US-049 quedaba en ``manual``: la migración 0008
    # le había puesto ``validacion_terreno`` a los rechazos viejos, pero cada
    # rechazo nuevo se asentaba como manual y el panel —que reconoce al
    # validador por el origen— dejaba de mostrarlo como decisión suya.
    Transition(
        operation="rechazar",
        source=Report.Status.PENDIENTE_VALIDACION,
        target=Report.Status.CANCELADO,
        actor=Actor.VALIDATOR,
        requires_reason=True,
        origin=Origin.VALIDACION_TERRENO,
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
    # Moderación municipal de contenido (US-049). El descarte lleva a
    # *Cancelado* y no a *Archivado*: cancelado significa "no era un problema
    # real", lo mismo que cuando lo rechaza el validador; archivado significa
    # "caducó", y es reversible por el municipio. Mezclarlos arruinaría las
    # métricas del municipio (US-050).
    #
    # Es **una sola operación** con una fila por estado de origen: la tabla
    # sigue teniendo un origen por fila, y ``apply_transition`` elige la que
    # corresponde al estado del reporte bloqueado.
    *(
        Transition(
            operation="descartar_por_moderacion",
            source=source,
            target=Report.Status.CANCELADO,
            actor=Actor.MUNICIPAL_AGENT,
            requires_reason=True,
            origin=Origin.MODERACION_MUNICIPAL,
            guard=_has_pending_content_complaints,
        )
        for source in MODERATION_SOURCES
    ),
    # La reversión de un descarte (US-049): una operación por destino, porque
    # desde *Cancelado* hay que poder volver a cualquiera de los estados del
    # descarte. La guarda impide elegir uno que no sea el que tenía.
    #
    # La ejecuta el administrador —de oficio o al hacer lugar a una
    # apelación— y también el agente de la jurisdicción al hacer lugar a una
    # apelación: decisión del usuario del 20/10, contraria a la historia, que
    # dejaba la apelación solo en manos de la plataforma.
    *(
        Transition(
            operation=restore_operation(status),
            source=Report.Status.CANCELADO,
            target=status,
            actor=Actor.PLATFORM_ADMIN,
            extra_actors=frozenset({Actor.MUNICIPAL_AGENT}),
            requires_reason=True,
            origin=Origin.REVERSION_MODERACION,
            guard=_restores_status(status),
        )
        for status in MODERATION_SOURCES
    ),
)

#: Orígenes de las transiciones que el panel **no** ofrece como botón: se
#: ejecutan desde la bandeja de denuncias o desde la revisión del
#: administrador, que es donde está el contexto que las justifica.
MODERATION_ORIGINS = frozenset(
    {Origin.MODERACION_MUNICIPAL, Origin.REVERSION_MODERACION},
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

#: Estados finales del circuito: no se sale de ellos con las acciones de
#: gestión del panel. Resuelto no tiene ninguna transición de salida. Cancelado
#: solo sale por la restitución de un descarte por moderación (US-049), una
#: fila ``restituir_a_<estado>`` por estado de origen: la ejecuta el
#: administrador, de oficio o al hacer lugar a una apelación, y también el agente
#: de la jurisdicción al hacer lugar a una apelación (decisión del 20/10). Hoy
#: ningún módulo importa esta constante.
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



def transitions_for(operation: str) -> tuple[Transition, ...]:
    """Las filas de una operación: una, o una por estado de origen (US-049)."""
    return tuple(t for t in TRANSITIONS if t.operation == operation)


def get_transition(operation: str, source: str | None = None) -> Transition | None:
    """La fila de ``operation``; con ``source``, la que sale de ese estado."""
    return next(
        (
            t
            for t in transitions_for(operation)
            if source is None or t.source == source
        ),
        None,
    )


def transitions_from(status: str, actor: Actor | None = None) -> tuple[Transition, ...]:
    """Transiciones disponibles desde ``status``.

    El panel las consume para renderizar solo las acciones posibles, en lugar de
    dibujar cinco botones y deshabilitar cuatro.
    """
    return tuple(
        transition
        for transition in TRANSITIONS
        if transition.source == status and (actor is None or transition.allows(actor))
    )


def is_valid(source: str, target: str, actor: Actor | None = None) -> bool:
    return any(
        transition.source == source
        and transition.target == target
        and (actor is None or transition.allows(actor))
        for transition in TRANSITIONS
    )
