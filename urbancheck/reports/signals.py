"""Evento único de cambio de estado (US-013, consumido por US-011).

Toda transición de la máquina de estados lo emite, sin importar desde qué
endpoint se haya ejecutado. Es el punto del que cuelgan las notificaciones: si
mañana aparece una transición nueva, el aviso sale solo.
"""

from django.dispatch import Signal

#: Argumentos: ``report``, ``previous_status``, ``new_status``, ``changed_by``,
#: ``reason``, ``history`` (el asiento recién escrito).
report_status_changed = Signal()
