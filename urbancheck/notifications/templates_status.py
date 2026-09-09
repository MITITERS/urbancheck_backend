"""Redacción de los avisos de cambio de estado (US-011).

Un mapeo declarativo de transición a mensaje, en un solo archivo: si aparece una
transición nueva, se agrega una fila acá y no un ``if`` más en el pipeline.

Los textos están en español y sin jerga: el vecino no tiene por qué leer los
nombres internos de los estados si hay una forma más clara de decirlo.
"""

from urbancheck.reports.models import Report
from urbancheck.reports.state_machine import Origin

Status = Report.Status

#: (estado anterior, estado nuevo) -> mensaje para el autor del reporte.
STATUS_CHANGE_MESSAGES: dict[tuple[str, str], str] = {
    (Status.PENDIENTE_VALIDACION, Status.REPORTADO): (
        "Un validador confirmó tu reporte en el lugar: ya es visible para la "
        "comunidad."
    ),
    (Status.PENDIENTE_VALIDACION, Status.CANCELADO): (
        "Tu reporte fue cancelado tras la verificación en terreno."
    ),
    (Status.REPORTADO, Status.EN_PROCESO): (
        "El municipio comenzó a trabajar en tu reporte."
    ),
    # US-046 cambió el camino a Resuelto: el operario cierra y el reporte queda
    # a la espera de que el autor lo objete o deje vencer el plazo.
    (Status.EN_PROCESO, Status.RESUELTO_PENDIENTE): (
        "El municipio resolvió tu reporte y cargó la evidencia del trabajo. "
        "Revisala: si el problema sigue, podés objetar el cierre."
    ),
    (Status.RESUELTO_PENDIENTE, Status.RESUELTO): (
        "Tu reporte quedó confirmado como resuelto."
    ),
    (Status.RESUELTO_PENDIENTE, Status.EN_PROCESO): (
        "Tu objeción se registró: el reporte volvió a gestión del área "
        "responsable."
    ),
    # Segundo cierre tras una apelación: es definitivo y no abre plazo nuevo.
    (Status.EN_PROCESO, Status.RESUELTO): (
        "El municipio volvió a intervenir y dio por resuelto tu reporte."
    ),
    (Status.EN_PROCESO, Status.CANCELADO): (
        "El municipio canceló la intervención sobre tu reporte."
    ),
    (Status.EN_PROCESO, Status.ARCHIVADO): (
        "Tu reporte fue archivado por el municipio."
    ),
    (Status.ARCHIVADO, Status.REPORTADO): (
        "Tu reporte fue reactivado y vuelve a estar visible."
    ),
    # Archivado automático por inactividad (US-031). El texto explica el motivo
    # sin nombrar estados internos: para el vecino lo que pasó es que su reporte
    # no consiguió validarse ni movió a nadie en medio año.
    (Status.PENDIENTE_VALIDACION, Status.ARCHIVADO): (
        "Tu reporte se archivó automáticamente: pasaron 180 días sin que "
        "lograra validarse ni recibiera interacción de la comunidad."
    ),
}

#: (estado anterior, estado nuevo, origen) -> mensaje, cuando el par de estados
#: **no alcanza** para redactar el aviso.
#:
#: Tiene prioridad sobre el mapa de arriba. Existe porque un mismo par puede
#: significar cosas distintas: desde US-040 se llega a *Reportado* desde
#: *Pendiente de validación* por dos caminos —un validador que fue al lugar
#: (US-036) o las confirmaciones de los vecinos—, y el aviso indexado solo por
#: el par le atribuía al vecino un validador que nunca existió.
#:
#: Es la misma lección que el panel ya había aprendido en ``get_validation()``:
#: **el discriminador es el origen, no la forma de la transición.** Se agrega
#: una fila acá cuando aparezca otro par ambiguo, no un ``if``.
ORIGIN_CHANGE_MESSAGES: dict[tuple[str, str, str], str] = {
    (Status.PENDIENTE_VALIDACION, Status.REPORTADO, Origin.VALIDACION_COLECTIVA): (
        "Varios vecinos confirmaron tu reporte: se validó automáticamente y ya "
        "es visible para la comunidad."
    ),
}

#: Se usa si apareciera una transición sin mensaje propio, para que el aviso
#: salga igual en lugar de perderse.
FALLBACK_MESSAGE = "Tu reporte cambió de estado."


def message_for(
    previous_status: str,
    new_status: str,
    reason: str = "",
    origin: str = "",
) -> str:
    """El texto del aviso para el autor.

    El origen es opcional y solo desempata: sin él se cae al mapa por par de
    estados, que sigue siendo el caso general. Así una transición nueva no
    obliga a tocar nada mientras su par sea inequívoco.
    """
    text = ORIGIN_CHANGE_MESSAGES.get(
        (previous_status, new_status, origin),
    ) or STATUS_CHANGE_MESSAGES.get((previous_status, new_status), FALLBACK_MESSAGE)
    if reason:
        text = f"{text} Motivo: {reason}"
    return text
