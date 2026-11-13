"""Validación colectiva de un reporte por umbral de confirmaciones (US-040).

Es el **segundo** camino hacia *Reportado*. A diferencia de la validación en
terreno de US-036, no exige presencia física: se apoya en cuántos vecinos
distintos confirmaron que el problema existe. Los dos caminos llegan al mismo
estado y certifican cosas distintas, y por eso la transición queda asentada con
un origen propio.

**Riesgo asumido y documentado.** El mecanismo es falseable con cuentas creadas
al efecto. Lo que hay acá son controles de *mitigación*, no de prevención: un me
gusta por usuario (la restricción de unicidad de ``Like``), exclusión del autor,
exclusión de las cuentas de trabajo y umbral parametrizable. La detección de
cuentas fraudulentas queda fuera del alcance del proyecto.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction

from .models import Report
from .services import TransitionError
from .services import apply_transition
from .state_machine import Actor

#: Operación de la máquina de estados que ejecuta este módulo.
COLLECTIVE_OPERATION = "validar_colectivamente"


def threshold() -> int:
    """Cuántas confirmaciones hacen falta, según la configuración vigente.

    Se lee en cada evaluación y no se cachea a nivel de módulo: el escenario 7
    pide que cambiar el valor no requiera redeploy, y una constante capturada al
    importar seguiría sirviendo el número viejo hasta reiniciar el proceso.
    """
    return settings.COLLECTIVE_VALIDATION_THRESHOLD


def evaluate(report: Report, *, actor=None) -> Report | None:
    """Valida el reporte si sus confirmaciones alcanzaron el umbral.

    Se llama **sincrónicamente al persistir un me gusta**, no desde un job
    periódico: un reporte que llegó al umbral tiene que pasar a *Reportado* en el
    momento, no horas después.

    Devuelve el reporte ya movido, o ``None`` si no correspondía hacer nada —que
    es el caso de la enorme mayoría de los me gusta—.

    El bloqueo de la fila serializa las evaluaciones de ese reporte: sin él, dos
    me gusta que cruzan el umbral a la vez producirían dos transiciones y dos
    asientos en el historial. El segundo encuentra el estado ya cambiado y sale
    por la guarda de estado de la máquina.
    """
    if report.status != Report.Status.PENDIENTE_VALIDACION:
        # Un reporte ya validado, rechazado o archivado no se mueve por me
        # gusta: el contador público se actualiza igual, pero nada más. Un
        # reporte que un validador rechazó no puede ser resucitado por likes.
        return None

    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.status != Report.Status.PENDIENTE_VALIDACION:
            return None

        confirmations = locked.confirmation_count()
        if confirmations < threshold():
            return None

        try:
            apply_transition(
                locked,
                COLLECTIVE_OPERATION,
                actor=Actor.SYSTEM,
                # Sin responsable individual: no la decidió una persona, la
                # decidió la cantidad. Quiénes confirmaron no se expone (US-038).
                changed_by=None,
                confirmation_count=confirmations,
            )
        except TransitionError:
            # Otra transacción la ejecutó entre la lectura y el intento. No es
            # un error: el reporte ya está donde se lo quería dejar.
            return None

    report.refresh_from_db()
    return report
