"""Función única de visibilidad, recorrida en todos sus puntos (Sprint 5, 6.1).

Un reporte es visible para alguien distinto de su autor solo si su estado es
visible, su imagen está procesada y no tiene una revisión por dato personal en
curso. Este módulo arma un reporte que **no** cumple alguna de las tres —de seis
formas distintas— y verifica que ningún punto de la lista lo devuelva: feed,
mapa, búsqueda, detalle por id, perfil público, bandeja de validación, me
gusta (que en este producto es la confirmación de US-040), comentarios y
denuncias.

El panel municipal es la excepción declarada: el agente gestiona también lo
cancelado, lo archivado y lo que espera el difuminado (decisión del equipo,
US-042). Lo que el panel **no** muestra nunca es una imagen sin procesar ni la
que está en revisión por dato personal.

Un caso de control con un reporte visible corre los mismos puntos y lo
encuentra en todos: sin él, el barrido pasaría igual con una API rota.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.tests.factories import ReportComplaintFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

#: Una palabra que solo está en la descripción del reporte, para la búsqueda.
NEEDLE = "Socavónúnico"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def ids(response) -> set[int]:
    data = response.data
    rows = data["results"] if isinstance(data, dict) else data
    return {row["id"] for row in rows}


def make_invisible(report: Report, how: str) -> None:
    if how in {"cancelado", "archivado"}:
        status = (
            Report.Status.CANCELADO if how == "cancelado" else Report.Status.ARCHIVADO
        )
        Report.objects.filter(pk=report.pk).update(status=status)
    elif how in {"imagen_pendiente", "imagen_fallida"}:
        report.photo.delete(save=False)
        Report.objects.filter(pk=report.pk).update(
            photo="",
            photo_status=(
                PhotoStatus.PENDIENTE
                if how == "imagen_pendiente"
                else PhotoStatus.FALLIDA
            ),
        )
    elif how == "revision_dato_personal":
        ReportComplaintFactory.create(report=report)
    elif how == "retirado":
        report.photo.delete(save=False)
        Report.objects.filter(pk=report.pk).update(
            photo="",
            photo_removed_at=timezone.now(),
        )
    report.refresh_from_db()


HOW = [
    "cancelado",
    "archivado",
    "imagen_pendiente",
    "imagen_fallida",
    "revision_dato_personal",
    "retirado",
]


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def report(active_municipality, author):
    return ReportFactory.create(
        author=author,
        municipality=active_municipality,
        status=Report.Status.PENDIENTE_VALIDACION,
        description=f"Hay un {NEEDLE} en la esquina.",
        latitude="-32.410300",
        longitude="-63.240000",
    )


@pytest.fixture
def neighbour():
    return client_for(UserFactory.create())


@pytest.fixture
def validator(active_municipality):
    return client_for(ValidatorFactory.create(municipality=active_municipality))


@pytest.fixture
def agent(active_municipality):
    return client_for(MunicipalAgentFactory.create(municipality=active_municipality))


def sweep(report, author, neighbour, validator) -> dict[str, bool]:
    """Si cada punto de la lista devuelve el reporte, o deja interactuar con él."""
    pk = report.pk
    found = {
        "feed": pk in ids(neighbour.get("/api/reports/")),
        "mapa": pk in ids(neighbour.get("/api/reports/map/")),
        "busqueda": pk in ids(neighbour.get("/api/reports/", {"search": NEEDLE})),
        "detalle": neighbour.get(f"/api/reports/{pk}/").status_code == HTTPStatus.OK,
        "perfil_publico": (
            neighbour.get(f"/api/users/{author.pk}/").data["report_count"] > 0
        ),
        "reportes_del_perfil": pk
        in ids(neighbour.get("/api/reports/", {"author": author.pk})),
        "bandeja_validacion": pk in ids(validator.get("/api/validation/reports/")),
        "me_gusta": (
            neighbour.post(f"/api/reports/{pk}/like/").status_code == HTTPStatus.CREATED
        ),
        "ver_comentarios": (
            neighbour.get(f"/api/reports/{pk}/comments/").status_code == HTTPStatus.OK
        ),
        "comentar": (
            neighbour.post(
                f"/api/reports/{pk}/comments/",
                {"text": "Lo vi."},
                format="json",
            ).status_code
            == HTTPStatus.CREATED
        ),
        "denunciar": (
            neighbour.post(
                f"/api/reports/{pk}/complaints/",
                {"reason": ReportComplaint.Reason.REPORTE_FALSO},
                format="json",
            ).status_code
            == HTTPStatus.CREATED
        ),
    }
    if report.status != Report.Status.PENDIENTE_VALIDACION:
        # La bandeja lista solo pendientes; un cancelado o archivado no
        # estaría ni siendo visible.
        found.pop("bandeja_validacion")
    return found


def test_a_visible_report_shows_up_everywhere(report, author, neighbour, validator):
    """CP-VIS-00: control. El mismo barrido encuentra un reporte visible."""
    found = sweep(report, author, neighbour, validator)

    assert all(found.values()), found


@pytest.mark.parametrize("how", HOW)
def test_an_invisible_report_shows_up_nowhere(
    report,
    author,
    neighbour,
    validator,
    how,
):
    """CP-VIS-01: ningún punto del 6.1 devuelve un reporte no visible."""
    make_invisible(report, how)

    found = sweep(report, author, neighbour, validator)

    assert not any(found.values()), {k: v for k, v in found.items() if v}
    assert not report.likes.exists()
    assert not report.comments.exists()
    assert not ReportComplaint.objects.filter(
        report=report,
        reason=ReportComplaint.Reason.REPORTE_FALSO,
    ).exists()


@pytest.mark.parametrize("how", HOW)
def test_the_author_still_sees_their_own(report, author, how):
    """CP-VIS-05: el autor ve su propio reporte, en el estado que esté."""
    make_invisible(report, how)
    client = client_for(author)

    assert client.get(f"/api/reports/{report.pk}/").status_code == HTTPStatus.OK
    assert report.pk in ids(client.get("/api/reports/", {"mine": "true"}))


@pytest.mark.parametrize("how", HOW)
def test_the_panel_never_serves_an_image_that_is_not_public(report, agent, how):
    """CP-VIS-06: el panel lista el reporte, pero nunca una imagen no pública.

    Se exceptúan cancelado y archivado: su imagen está difuminada y es parte de
    lo que el agente gestiona.
    """
    make_invisible(report, how)

    listed = report.pk in ids(
        agent.get("/api/panel/reports/", {"status": report.status}),
    )
    detail = agent.get(f"/api/panel/reports/{report.pk}/").data

    assert listed
    assert "photo_pending" not in detail
    if how not in {"cancelado", "archivado"}:
        assert detail["photo"] is None
