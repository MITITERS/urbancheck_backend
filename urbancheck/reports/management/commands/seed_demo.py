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
from PIL import Image

from urbancheck.municipalities.models import Municipality
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.users.models import User

DEFAULT_PASSWORD = "Urbancheck2026!"  # noqa: S105

# Centros reales y radios que no se pisan: son los que deciden a qué municipio
# le llega cada reporte.
MUNICIPALITY = {
    "city": "Villa María",
    "province": "Córdoba",
    "latitude": -32.4103,
    "longitude": -63.2400,
    "coverage_radius_km": 15,
}
SECOND_MUNICIPALITY = {
    "city": "Villa Nueva",
    "province": "Córdoba",
    "latitude": -32.4333,
    "longitude": -63.2333,
    "coverage_radius_km": 8,
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
]


def _placeholder_photo() -> ContentFile:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(120, 140, 160)).save(buffer, format="JPEG")
    return ContentFile(buffer.getvalue(), name="seed.jpg")


class Command(BaseCommand):
    help = "Crea municipalidad, usuarios de cada rol y reportes en los seis estados."

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

        created = self._seed_reports(citizen, municipality)
        created += self._seed_reports(citizen, other, offset=len(SEED_REPORTS))

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Municipalidad activa: {municipality} (id={municipality.pk}). "
                f"Usuarios: {admin.email}, {agent.email}, {validator.email}, "
                f"{citizen.email} (contraseña: {password}). "
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

    def _upsert_user(self, email, name, role, municipality, password) -> User:
        user, _ = User.objects.update_or_create(
            email=email,
            defaults={
                "name": name,
                "role": role,
                "municipality": municipality,
                "must_change_password": False,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password"])
        return user

    def _seed_reports(self, author, municipality, offset: int = 0) -> int:
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
            )
            ReportStatusHistory.objects.create(
                report=report,
                status=status,
                changed_by=author,
            )
            created += 1
        return created
