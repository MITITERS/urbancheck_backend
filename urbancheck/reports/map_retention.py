"""Cuánto tiempo sigue dibujado en el mapa un reporte ya resuelto.

Un reporte resuelto sigue siendo cierto, pero deja de ser una problemática
urbana **vigente**. El mapa responde «¿qué pasa hoy en mi barrio?», y con los
resueltos de todos los meses encima termina respondiendo «¿qué pasó alguna
vez?»: el vecino abre la pestaña y ve una nube de puntos verdes donde ya no hay
nada que mirar.

**Sale del mapa y de ningún otro lado.** Sigue en el feed, en el detalle, en el
perfil de su autor y en el panel del municipio. No se archiva, no cambia de
estado y no se borra: es una regla de *qué se dibuja*, no de qué existe, y por
eso vive acá y no en la máquina de estados. Es la diferencia con el archivado
por inactividad de US-031, que sí mueve el reporte de estado.

Alcanza **solo** a *Resuelto*. *Resuelto, a confirmar* se queda: mientras corre
la ventana de objeción el caso está abierto, y esconderlo del mapa justo cuando
el vecino puede querer revisarlo sería esconderle lo que tiene que decidir.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.utils import timezone

from .models import Report
from .models import ReportStatusHistory


def retention_window() -> timedelta:
    """Cuánto queda dibujado un reporte después de resolverse.

    Se lee de configuración en cada consulta, y **en minutos** por lo mismo que
    la ventana de objeción de US-047: el default son quince días, pero mostrar
    esto en una demostración exige poder bajarlo a un par de minutos sin tocar
    código ni esperar dos semanas.
    """
    return timedelta(minutes=settings.MAP_RESOLVED_RETENTION_MINUTES)


def hide_stale_resolved(queryset, now=None):
    """Saca del mapa los reportes resueltos hace más que la ventana.

    La fecha sale del **historial de estados** y no de ``Report.closed_at``: ese
    campo guarda cuándo el operario cerró el trabajo, que es hasta una semana
    antes de que el reporte quede efectivamente *Resuelto* —en el medio corre la
    ventana de objeción de US-047—. Contar desde ahí adelantaría la desaparición
    de todos los reportes en esa diferencia.

    Va por subconsulta y no por ``JOIN``, con el mismo criterio que el resto de
    las lecturas del historial: el ``JOIN`` duplicaría la fila si algún día un
    reporte llegara a *Resuelto* más de una vez.

    Un reporte resuelto **sin** asiento en el historial se queda dibujado. Es un
    caso que no debería existir —toda transición deja asiento—, y ante la duda
    el default es mostrar de más y no esconder de menos.

    Ese último caso necesita el ``isnull=False`` explícito, y no es decorativo:
    sin él la fila desaparecía. SQL tiene tres valores, y ``NULL < fecha`` no da
    falso sino ``NULL``; ``NOT (NULL AND verdadero)`` vuelve a dar ``NULL``, y un
    ``WHERE`` que no da verdadero descarta la fila. O sea que la condición hacía
    exactamente lo contrario de lo que este párrafo promete.
    """
    now = now or timezone.now()
    resolved_at = ReportStatusHistory.objects.filter(
        report=OuterRef("pk"),
        status=Report.Status.RESUELTO,
    ).order_by("-created_at")

    return queryset.annotate(
        resolved_at=Subquery(resolved_at.values("created_at")[:1]),
    ).exclude(
        Q(status=Report.Status.RESUELTO)
        & Q(resolved_at__isnull=False)
        & Q(resolved_at__lt=now - retention_window()),
    )
