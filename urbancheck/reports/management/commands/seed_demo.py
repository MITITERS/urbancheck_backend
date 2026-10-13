"""Datos de demostración para desarrollar y probar el panel.

Es el "trabajo previo" del sprint: rompe la dependencia falsa entre el panel
(US-012 y US-013) y la validación en terreno (US-036), porque genera reportes en
los seis estados sin necesidad de que exista el flujo de validación.

    docker compose -f docker-compose.local.yml exec django /entrypoint \\
        python manage.py seed_demo

Es idempotente: se puede correr varias veces sin duplicar usuarios ni
municipalidades.
"""

import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image

from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.models import OperationalArea
from urbancheck.reports.models import Report
from urbancheck.reports.models import ResolutionEvidence
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.users.models import User

DEFAULT_PASSWORD = "Urbancheck2026!"  # noqa: S105

# Villa María y Villa Nueva son el caso que motivó pasar de círculos a
# polígonos: están pegadas y las separa el río Ctalamochita. Con círculos, uno
# lo bastante grande para cubrir Villa María entera se comía media Villa Nueva.
#
# Estos dos polígonos son rectángulos aproximados que comparten el borde del
# río —no son los límites catastrales reales, alcanza para poblar una demo— y
# lo importante es que **no se superponen**: cada reporte cae en uno solo.
RIVER_LATITUDE = -32.4250

MUNICIPALITY = {
    "city": "Villa María",
    "province": "Córdoba",
    "latitude": -32.4103,
    "longitude": -63.2400,
    # Al norte del río.
    "boundary": [
        [-32.3800, -63.2900],
        [-32.3800, -63.1950],
        [RIVER_LATITUDE, -63.1950],
        [RIVER_LATITUDE, -63.2900],
    ],
}
SECOND_MUNICIPALITY = {
    "city": "Villa Nueva",
    "province": "Córdoba",
    "latitude": -32.4400,
    "longitude": -63.2300,
    # Al sur del río, pegada a la anterior y sin pisarla.
    "boundary": [
        [RIVER_LATITUDE, -63.2700],
        [RIVER_LATITUDE, -63.1900],
        [-32.4620, -63.1900],
        [-32.4620, -63.2700],
    ],
}

CENTER = (-32.4103, -63.2400)

SEED_REPORTS = [
    (
        Report.Status.PENDIENTE_VALIDACION,
        Report.Category.BACHE,
        "Bache profundo sobre la calzada",
    ),
    (
        Report.Status.PENDIENTE_VALIDACION,
        Report.Category.BASURA,
        "Basura acumulada en la vereda",
    ),
    (
        Report.Status.REPORTADO,
        Report.Category.ALUMBRADO,
        "Luminaria apagada hace una semana",
    ),
    (Report.Status.REPORTADO, Report.Category.SEMAFORO, "Semáforo intermitente"),
    (Report.Status.EN_PROCESO, Report.Category.VEREDA, "Vereda levantada por raíces"),
    (Report.Status.RESUELTO, Report.Category.BACHE, "Bache ya reparado"),
    (Report.Status.CANCELADO, Report.Category.OTRO, "Reclamo duplicado"),
    (Report.Status.ARCHIVADO, Report.Category.BASURA, "Contenedor retirado"),
    # El estado que agregó US-046 va **al final** y no en su lugar lógico: el
    # seed es idempotente por el índice de esta lista, así que insertar en el
    # medio correría los marcadores de todo lo que viene después y una base ya
    # sembrada terminaría con los reportes duplicados.
    (
        Report.Status.RESUELTO_PENDIENTE,
        Report.Category.ALUMBRADO,
        "Luminaria repuesta, a la espera de que el vecino confirme",
    ),
]


#: Estados que solo se alcanzan pasando por la asignación a un área (US-028).
#: *Archivado* y *Cancelado* quedan afuera: se llega a ellos también desde
#: estados anteriores a la gestión.
ASSIGNED_STATUSES = frozenset(
    {
        Report.Status.EN_PROCESO,
        Report.Status.RESUELTO_PENDIENTE,
        Report.Status.RESUELTO,
    },
)

#: Estados a los que solo se llega con un cierre de operario detrás (US-046).
#: El seed les crea la evidencia: un reporte resuelto sin parte de trabajo es un
#: estado que el circuito real no puede producir.
CLOSED_STATUSES = frozenset(
    {Report.Status.RESUELTO_PENDIENTE, Report.Status.RESUELTO},
)


def _placeholder_photo() -> ContentFile:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(120, 140, 160)).save(buffer, format="JPEG")
    return ContentFile(buffer.getvalue(), name="seed.jpg")


class Command(BaseCommand):
    help = (
        "Crea municipalidad, área operativa, usuarios de cada rol y reportes en "
        "los seis estados."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Contraseña de todos los usuarios de demo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]

        municipality = self._upsert_municipality(MUNICIPALITY)
        # Un segundo municipio poblado es lo que hace visible una fuga de
        # jurisdicción mientras se desarrolla, y no recién en los tests.
        other = self._upsert_municipality(SECOND_MUNICIPALITY)

        admin = self._upsert_user(
            "admin@urbancheck.test",
            "Admin Plataforma",
            User.Role.ADMIN_PLATAFORMA,
            None,
            password,
        )
        agent = self._upsert_user(
            "agente@urbancheck.test",
            "Agente Villa María",
            User.Role.AGENTE_MUNICIPAL,
            municipality,
            password,
        )
        validator = self._upsert_user(
            "validador@urbancheck.test",
            "Validador Villa María",
            User.Role.VALIDADOR,
            municipality,
            password,
        )
        citizen = self._upsert_user(
            "vecino@urbancheck.test",
            "Vecina Ejemplo",
            User.Role.CIUDADANO,
            None,
            password,
        )

        # Un área por municipio: desde US-028 un reporte En proceso sin área
        # responsable no puede existir, así que el seed tampoco puede fabricarlo.
        area = self._upsert_area(municipality)
        other_area = self._upsert_area(other)
        operator = self._upsert_user(
            "operario@urbancheck.test",
            "Operario Villa María",
            User.Role.OPERARIO,
            municipality,
            password,
            operational_area=area,
        )

        created = self._seed_reports(citizen, municipality, area=area, operator=operator)
        created += self._seed_reports(
            citizen,
            other,
            area=other_area,
            # El otro municipio no tiene operario propio: sus reportes cerrados
            # quedan sin parte de trabajo, que es lo correcto — nadie los cerró.
            operator=None,
            offset=len(SEED_REPORTS),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Municipalidad activa: {municipality} (id={municipality.pk}). "
                f"Usuarios: {admin.email}, {agent.email}, {validator.email}, "
                f"{operator.email}, {citizen.email} (contraseña: {password}). "
                f"Reportes nuevos: {created}.",
            ),
        )
        self.stdout.write(
            "Con más de una municipalidad cargada, los reportes nuevos necesitan "
            f"saber cuál es la activa: DJANGO_ACTIVE_MUNICIPALITY_ID={municipality.pk}",
        )

    def _upsert_municipality(self, data: dict) -> Municipality:
        municipality, _ = Municipality.objects.update_or_create(
            city=data["city"],
            province=data["province"],
            defaults={k: v for k, v in data.items() if k not in ("city", "province")},
        )
        return municipality

    def _upsert_area(self, municipality: Municipality) -> OperationalArea:
        area, _ = OperationalArea.objects.update_or_create(
            municipality=municipality,
            name="Obras Públicas",
            defaults={
                "contact_email": "obras@urbancheck.test",
                "contact_phone": "3534123456",
                "is_active": True,
            },
        )
        return area

    def _upsert_user(  # noqa: PLR0913 (un parámetro por dato del alta)
        self,
        email,
        name,
        role,
        municipality,
        password,
        operational_area=None,
    ) -> User:
        user, _ = User.objects.update_or_create(
            email=email,
            defaults={
                "name": name,
                "role": role,
                "municipality": municipality,
                "operational_area": operational_area,
                "must_change_password": False,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password"])
        return user

    def _seed_reports(  # noqa: PLR0913 (un parámetro por dato del alta)
        self,
        author,
        municipality,
        *,
        area,
        operator=None,
        offset: int = 0,
    ) -> int:
        created = 0
        for index, (status, category, description) in enumerate(SEED_REPORTS):
            marker = f"[seed:{municipality.pk}:{index}]"
            if Report.objects.filter(description__endswith=marker).exists():
                continue
            report = Report.objects.create(
                author=author,
                municipality=municipality,
                photo=_placeholder_photo(),
                description=f"{description} {marker}",
                category=category,
                latitude=CENTER[0] + (index + offset) * 0.001,
                longitude=CENTER[1] + (index + offset) * 0.001,
                address=f"Calle {index + 1}, {municipality.city}",
                status=status,
                # Los estados que solo se alcanzan pasando por la gestión
                # municipal llevan área responsable: es el invariante de US-028.
                operational_area=area if status in ASSIGNED_STATUSES else None,
                area_assigned_at=(
                    timezone.now() if status in ASSIGNED_STATUSES else None
                ),
                closed_at=timezone.now() if status in CLOSED_STATUSES else None,
            )
            if status in CLOSED_STATUSES and operator is not None:
                ResolutionEvidence.objects.create(
                    report=report,
                    photo=_placeholder_photo(),
                    description=(
                        "Se ejecutó el trabajo en el lugar y quedó verificado."
                    ),
                    operator=operator,
                    operational_area=area,
                    latitude=report.latitude,
                    longitude=report.longitude,
                )
            ReportStatusHistory.objects.create(
                report=report,
                status=status,
                changed_by=author,
            )
            created += 1
        return created
