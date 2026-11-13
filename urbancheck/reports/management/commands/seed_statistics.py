"""Reportes con historia, para que la sección de estadísticas tenga qué mostrar.

``seed_demo`` deja un reporte por estado, creado hoy y con un solo asiento en el
historial: alcanza para el listado, pero las estadísticas (US-023 y US-050) se
ven vacías o planas. Este comando agrega, por municipalidad de demo, reportes
repartidos en los últimos 12 meses entre categorías y estados, cada uno con su
cadena de transiciones fechada y con el origen que le corresponde.

    docker compose -f docker-compose.local.yml exec django /entrypoint \\
        python manage.py seed_statistics

Va aparte de ``seed_demo`` porque aquel es idempotente por el índice de su
lista, y sumarle cien reportes lo volvería ilegible. Este también es idempotente
—por un marcador en la descripción— y determinista: la misma corrida genera
siempre los mismos datos.

Las transiciones se escriben **directo** en el historial, sin pasar por
``apply_transition``: hay que fecharlas en el pasado, y la máquina de estados
—con razón— las fecha ahora. Cada cadena es una de las que la máquina admite.
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.models import OperationalArea
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.models import ResolutionAppeal
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.state_machine import Origin
from urbancheck.users.models import User

from .seed_demo import CENTER
from .seed_demo import MUNICIPALITY
from .seed_demo import SECOND_MUNICIPALITY

Status = Report.Status

REPORTS_PER_MUNICIPALITY = 90
DAYS_BACK = 365

#: Cómo termina cada reporte, con su peso. Cada camino es una lista de
#: transiciones ``(estado, origen)`` a partir de *Pendiente de validación*.
PATHS: list[tuple[int, list[tuple[str, str]]]] = [
    # Sigue esperando validación.
    (8, []),
    # Validado en terreno y esperando que el municipio lo tome.
    (6, [(Status.REPORTADO, Origin.VALIDACION_TERRENO)]),
    # Validado por la comunidad y en gestión.
    (
        6,
        [
            (Status.REPORTADO, Origin.VALIDACION_COLECTIVA),
            (Status.EN_PROCESO, Origin.MANUAL),
        ],
    ),
    # El circuito completo, confirmado por silencio del autor.
    (
        22,
        [
            (Status.REPORTADO, Origin.VALIDACION_TERRENO),
            (Status.EN_PROCESO, Origin.MANUAL),
            (Status.RESUELTO_PENDIENTE, Origin.CIERRE_OPERARIO),
            (Status.RESUELTO, Origin.CONFIRMACION_AUTOMATICA),
        ],
    ),
    # El circuito completo con validación colectiva y confirmación del agente.
    (
        10,
        [
            (Status.REPORTADO, Origin.VALIDACION_COLECTIVA),
            (Status.EN_PROCESO, Origin.MANUAL),
            (Status.RESUELTO_PENDIENTE, Origin.CIERRE_OPERARIO),
            (Status.RESUELTO, Origin.MANUAL),
        ],
    ),
    # Cerrado y en la ventana de objeción.
    (
        5,
        [
            (Status.REPORTADO, Origin.VALIDACION_TERRENO),
            (Status.EN_PROCESO, Origin.MANUAL),
            (Status.RESUELTO_PENDIENTE, Origin.CIERRE_OPERARIO),
        ],
    ),
    # Apelado y vuelto a cerrar, definitivo (US-048).
    (
        6,
        [
            (Status.REPORTADO, Origin.VALIDACION_TERRENO),
            (Status.EN_PROCESO, Origin.MANUAL),
            (Status.RESUELTO_PENDIENTE, Origin.CIERRE_OPERARIO),
            (Status.EN_PROCESO, Origin.APELACION_CIUDADANO),
            (Status.RESUELTO, Origin.CIERRE_OPERARIO),
        ],
    ),
    # Rechazado por el validador en terreno.
    (6, [(Status.CANCELADO, Origin.VALIDACION_TERRENO)]),
    # Descartado por moderación municipal (US-049).
    (
        3,
        [
            (Status.REPORTADO, Origin.VALIDACION_TERRENO),
            (Status.CANCELADO, Origin.MODERACION_MUNICIPAL),
        ],
    ),
    # Archivado por inactividad (US-031).
    (6, [(Status.ARCHIVADO, Origin.ARCHIVADO_INACTIVIDAD)]),
    # Cancelado por el municipio con la intervención en curso.
    (
        2,
        [
            (Status.REPORTADO, Origin.VALIDACION_TERRENO),
            (Status.EN_PROCESO, Origin.MANUAL),
            (Status.CANCELADO, Origin.MANUAL),
        ],
    ),
]

#: Cuánto tarda cada paso, en horas: (mínimo, máximo). Rangos distintos por
#: origen para que los tiempos de US-050 se puedan distinguir en la demo.
STEP_HOURS = {
    Origin.VALIDACION_TERRENO: (6, 96),
    Origin.VALIDACION_COLECTIVA: (24, 240),
    Origin.MANUAL: (4, 120),
    Origin.CIERRE_OPERARIO: (24, 336),
    Origin.CONFIRMACION_AUTOMATICA: (168, 170),
    Origin.APELACION_CIUDADANO: (12, 96),
    Origin.MODERACION_MUNICIPAL: (12, 72),
    Origin.ARCHIVADO_INACTIVIDAD: (2160, 2200),
}

CATEGORY_WEIGHTS = [
    (Report.Category.BACHE, 30),
    (Report.Category.ALUMBRADO, 20),
    (Report.Category.BASURA, 20),
    (Report.Category.VEREDA, 15),
    (Report.Category.SEMAFORO, 8),
    (Report.Category.OTRO, 7),
]

DESCRIPTIONS = {
    Report.Category.BACHE: "Bache sobre la calzada",
    Report.Category.ALUMBRADO: "Luminaria apagada",
    Report.Category.BASURA: "Residuos acumulados en la esquina",
    Report.Category.VEREDA: "Vereda rota",
    Report.Category.SEMAFORO: "Semáforo sin funcionar",
    Report.Category.OTRO: "Otro problema en la vía pública",
}


def _pick(rng: random.Random, weighted):
    return rng.choices(
        [item for item, _ in weighted],
        weights=[w for _, w in weighted],
    )[0]


class Command(BaseCommand):
    help = "Agrega reportes con historial fechado para la sección de estadísticas."

    @transaction.atomic
    def handle(self, *args, **options):
        citizen = User.objects.filter(email="vecino@urbancheck.test").first()
        if citizen is None:
            self.stderr.write("Corré primero seed_demo: falta la vecina de demo.")
            return
        created = 0
        for data in (MUNICIPALITY, SECOND_MUNICIPALITY):
            municipality = Municipality.objects.filter(
                city=data["city"],
                province=data["province"],
            ).first()
            if municipality is None:
                continue
            created += self._seed(municipality, citizen)
        self.stdout.write(self.style.SUCCESS(f"Listo. Reportes nuevos: {created}."))

    def _seed(self, municipality: Municipality, citizen: User) -> int:
        rng = random.Random(municipality.pk)  # noqa: S311 (datos de demo)
        area = OperationalArea.objects.filter(municipality=municipality).first()
        agent = User.objects.filter(
            role=User.Role.AGENTE_MUNICIPAL,
            municipality=municipality,
        ).first()
        validator = User.objects.filter(
            role=User.Role.VALIDADOR,
            municipality=municipality,
        ).first()
        operator = User.objects.filter(
            role=User.Role.OPERARIO,
            municipality=municipality,
        ).first()
        responsible = {
            Origin.VALIDACION_TERRENO: validator,
            Origin.MANUAL: agent,
            Origin.CIERRE_OPERARIO: operator,
            Origin.APELACION_CIUDADANO: citizen,
            Origin.MODERACION_MUNICIPAL: agent,
        }
        now = timezone.now()
        created = 0
        for index in range(REPORTS_PER_MUNICIPALITY):
            marker = f"[stats:{municipality.pk}:{index}]"
            category = _pick(rng, CATEGORY_WEIGHTS)
            path = _pick(rng, [(steps, weight) for weight, steps in PATHS])
            created_at = now - timedelta(
                days=rng.uniform(0, DAYS_BACK),
            )
            if Report.objects.filter(description__endswith=marker).exists():
                continue

            # Las transiciones, fechadas; las que caerían en el futuro se cortan
            # ahí: un reporte reciente todavía no llegó tan lejos.
            moment = created_at
            steps = []
            for status, origin in path:
                low, high = STEP_HOURS[origin]
                moment += timedelta(hours=rng.uniform(low, high))
                if moment >= now:
                    break
                steps.append((status, origin, moment))
            final = steps[-1][0] if steps else Status.PENDIENTE_VALIDACION
            assigned = any(status == Status.EN_PROCESO for status, _, _ in steps)
            closes = [m for _, origin, m in steps if origin == Origin.CIERRE_OPERARIO]
            appeals = [
                m for _, origin, m in steps if origin == Origin.APELACION_CIUDADANO
            ]

            report = Report.objects.create(
                author=citizen,
                municipality=municipality,
                description=f"{DESCRIPTIONS[category]} {marker}",
                category=category,
                latitude=CENTER[0] + rng.uniform(-0.02, 0.012),
                longitude=CENTER[1] + rng.uniform(-0.04, 0.04),
                address=f"Calle {rng.randint(1, 400)}, {municipality.city}",
                status=final,
                # Sin foto: no hay nada que difuminar, y así no pasa por Celery.
                photo_status=PhotoStatus.PROCESADA,
                operational_area=area if assigned else None,
                area_assigned_at=(
                    next(m for s, _, m in steps if s == Status.EN_PROCESO)
                    if assigned
                    else None
                ),
                closed_at=closes[-1] if closes else None,
                archived_at=steps[-1][2] if final == Status.ARCHIVADO else None,
                appeal_count=len(appeals),
            )
            Report.objects.filter(pk=report.pk).update(created_at=created_at)
            entries = [
                ReportStatusHistory(
                    report=report,
                    status=Status.PENDIENTE_VALIDACION,
                    changed_by=citizen,
                ),
            ]
            previous = Status.PENDIENTE_VALIDACION
            for status, origin, _ in steps:
                entries.append(
                    ReportStatusHistory(
                        report=report,
                        status=status,
                        previous_status=previous,
                        changed_by=responsible.get(origin),
                        origin=origin,
                    ),
                )
                previous = status
            ReportStatusHistory.objects.bulk_create(entries)
            # ``auto_now_add`` pisa la fecha al crear: se corrige después.
            dates = [created_at, *(m for _, _, m in steps)]
            for entry, moment in zip(entries, dates, strict=True):
                ReportStatusHistory.objects.filter(pk=entry.pk).update(
                    created_at=moment,
                )
            for moment in closes:
                evidence = ResolutionEvidence.objects.create(
                    report=report,
                    description="Se ejecutó el trabajo en el lugar.",
                    operator=operator,
                    operational_area=area,
                    latitude=report.latitude,
                    longitude=report.longitude,
                    photo_status=PhotoStatus.PROCESADA,
                )
                ResolutionEvidence.objects.filter(pk=evidence.pk).update(
                    created_at=moment,
                )
            for moment in appeals:
                appeal = ResolutionAppeal.objects.create(
                    report=report,
                    author=citizen,
                    reason="El problema sigue igual.",
                    photo_status=PhotoStatus.PROCESADA,
                )
                ResolutionAppeal.objects.filter(pk=appeal.pk).update(created_at=moment)
            created += 1
        return created
