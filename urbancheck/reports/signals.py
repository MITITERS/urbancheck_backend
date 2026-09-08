"""Evento único de cambio de estado (US-013, consumido por US-011).

Toda transición de la máquina de estados lo emite, sin importar desde qué
endpoint se haya ejecutado. Es el punto del que cuelgan las notificaciones: si
mañana aparece una transición nueva, el aviso sale solo.
"""

from django.dispatch import Signal

#: Argumentos: ``report``, ``previous_status``, ``new_status``, ``changed_by``,
#: ``reason``, ``history`` (el asiento recién escrito).
report_status_changed = Signal()

#: Se emite cuando un reporte queda vinculado a un área operativa (US-028), sea
#: por la asignación inicial que lo pone En proceso o por una reasignación
#: posterior. Argumentos: ``report``, ``assignment`` (el asiento recién
#: escrito), ``assigned_by``.
#:
#: Existe por lo mismo que ``report_status_changed``: la reasignación no cambia
#: el estado, así que quien quiera reaccionar a ella no puede escuchar aquel
#: evento. Se emite fuera de la transacción, con el mismo criterio.
report_area_assigned = Signal()
