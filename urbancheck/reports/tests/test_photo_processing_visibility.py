"""US-042 — un reporte no es público hasta que su imagen está difuminada.

Escenarios 1, 2, 3, 6 y 7: qué se ve y qué no mientras la foto se procesa,
quién puede operar sobre un reporte sin publicar, y por qué no hay ningún
camino que publique una imagen sin difuminar.

El circuito en sí —reintentos, fallo definitivo, aviso al autor— se prueba en
``anonymization/tests/test_deferred_publication.py``.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.anonymization.models import PhotoStatus
from urbancheck.municipalities.tests.factories import OperationalAreaFactory
from urbancheck.reports.archival import ARCHIVE_OPERATION
from urbancheck.reports.models import Report
from urbancheck.reports.services import apply_transition
from urbancheck.reports.state_machine import Actor
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

HERE = {"latitude": "-32.410300", "longitude": "-63.240000"}


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def listed_ids(response) -> set[int]:
    data = response.data
    rows = data["results"] if isinstance(data, dict) else data
    return {row["id"] for row in rows}


@pytest.fixture
def author():
    return UserFactory.create()


@pytest.fixture
def author_client(author) -> APIClient:
    return client_for(author)


@pytest.fixture
def neighbour_client() -> APIClient:
    return client_for(UserFactory.create())


@pytest.fixture
def processing(author, active_municipality):
    """Un reporte cuya imagen todavía está en la cola de difuminado."""
    return ReportFactory.create(
        author=author,
        municipality=active_municipality,
        status=Report.Status.PENDIENTE_VALIDACION,
        photo="",
        photo_pending="pending/report/original.jpg",
        photo_status=PhotoStatus.PENDIENTE,
        **HERE,
    )


class TestInvisibleWhileProcessing:
    """Escenario 2: para cualquiera que no sea el autor, todavía no existe."""

    def test_it_is_not_in_the_feed(self, processing, neighbour_client):
        assert processing.pk not in listed_ids(neighbour_client.get("/api/reports/"))

    def test_it_is_not_on_the_map(self, processing, neighbour_client):
        assert processing.pk not in listed_ids(
            neighbour_client.get("/api/reports/map/"),
        )

    def test_it_is_not_found_by_search(self, processing, neighbour_client):
        response = neighbour_client.get(
            "/api/reports/?search=" + processing.description,
        )
        assert processing.pk not in listed_ids(response)

    def test_it_cannot_be_opened_by_id(self, processing, neighbour_client):
        response = neighbour_client.get(f"/api/reports/{processing.pk}/")
        assert response.status_code == HTTP_NOT_FOUND

    def test_it_does_not_count_on_the_public_profile(
        self,
        processing,
        author,
        neighbour_client,
    ):
        """Un contador que no coincide con la lista es la pista de lo escondido.

        Contaba todos los reportes del autor, así que el perfil público
        delataba lo que ninguna vista mostraba. Ahora cuenta exactamente lo
        que un tercero puede abrir.
        """
        author.is_public = True
        author.save(update_fields=["is_public"])
        ReportFactory.create(author=author)

        response = neighbour_client.get(f"/api/users/{author.pk}/")

        assert response.data["report_count"] == 1


class TestTheAuthorSeesTheirOwn:
    """Escenario 3: ocultarle al autor su propio reporte no protege a nadie."""

    def test_it_is_in_their_own_history(self, processing, author_client):
        response = author_client.get("/api/reports/?mine=true")

        assert processing.pk in listed_ids(response)
        row = next(r for r in response.data["results"] if r["id"] == processing.pk)
        # El indicador explícito que pide el escenario: la app no tiene que
        # deducir de `photo: null` que todavía se está procesando.
        assert row["photo_status"] == PhotoStatus.PENDIENTE
        assert row["photo"] is None

    def test_they_can_open_it(self, processing, author_client):
        response = author_client.get(f"/api/reports/{processing.pk}/")

        assert response.status_code == HTTP_OK
        assert response.data["photo_status"] == PhotoStatus.PENDIENTE

    def test_they_can_still_delete_it(self, processing, author_client):
        response = author_client.delete(f"/api/reports/{processing.pk}/")

        assert response.status_code == HTTP_NO_CONTENT


class TestItDoesNotCountForCollectiveValidation:
    """Escenario 7: lo que nadie ve no recibe apoyo ni espera validación."""

    def test_a_neighbour_cannot_like_it(self, processing, neighbour_client):
        response = neighbour_client.post(f"/api/reports/{processing.pk}/like/")

        assert response.status_code == HTTP_NOT_FOUND

    def test_not_even_the_author_can_like_it(self, processing, author_client):
        """Más estricto que el detalle, y a propósito.

        El autor abre su reporte para ver que se está procesando, pero un
        reporte que nadie ve no puede acumular apoyos: si pudiera, el umbral de
        US-040 se alcanzaría sobre algo invisible.
        """
        response = author_client.post(f"/api/reports/{processing.pk}/like/")

        assert response.status_code == HTTP_NOT_FOUND

    def test_it_is_not_in_the_validation_inbox(self, processing, active_municipality):
        validator = ValidatorFactory.create(municipality=active_municipality)

        response = client_for(validator).get("/api/validation/reports/")

        assert processing.pk not in listed_ids(response)

    def test_the_validator_cannot_open_it_either(
        self,
        processing,
        active_municipality,
    ):
        validator = ValidatorFactory.create(municipality=active_municipality)

        response = client_for(validator).get(
            f"/api/validation/reports/{processing.pk}/",
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestThePanelSeesItButCannotPublishIt:
    """Escenario 6: el panel es la única vista que lo muestra, y no lo publica."""

    @pytest.fixture
    def agent_client(self, active_municipality) -> APIClient:
        return client_for(
            MunicipalAgentFactory.create(municipality=active_municipality),
        )

    def test_the_panel_lists_it_with_its_state(self, processing, agent_client):
        """El agente tiene que saber que el vecino todavía no lo ve.

        Sin el campo vería una tarjeta sin foto y sin explicación, que es
        indistinguible de una imagen retirada por protección de datos.
        """
        response = agent_client.get("/api/panel/reports/")

        assert processing.pk in listed_ids(response)
        row = next(r for r in response.data["results"] if r["id"] == processing.pk)
        assert row["photo_status"] == PhotoStatus.PENDIENTE

    def test_the_panel_cannot_manage_it(
        self,
        processing,
        agent_client,
        active_municipality,
    ):
        """Un reporte validado en terreno cuya foto todavía no se difuminó.

        Puede pasar: la validación colectiva de US-040 no es el único camino a
        *Reportado*. Lo que no puede pasar es que el municipio lo ponga en
        gestión, porque para el vecino ese reporte no existe.
        """
        area = OperationalAreaFactory.create(municipality=active_municipality)
        Report.objects.filter(pk=processing.pk).update(
            status=Report.Status.REPORTADO,
        )

        response = agent_client.post(
            f"/api/panel/reports/{processing.pk}/process/",
            {"area_id": area.pk},
            format="json",
        )

        assert response.status_code == HTTP_CONFLICT
        processing.refresh_from_db()
        assert processing.status == Report.Status.REPORTADO

    def test_it_offers_no_action_that_the_server_would_reject(
        self,
        processing,
        agent_client,
        active_municipality,
    ):
        """El panel dibuja los botones que esta lista trae, y nada más.

        Dejar la transición listada sería ofrecer una acción que el servidor
        rechaza con un 409 apenas se la aprieta.
        """
        Report.objects.filter(pk=processing.pk).update(
            status=Report.Status.REPORTADO,
        )

        detail = agent_client.get(f"/api/panel/reports/{processing.pk}/").data
        offered = {t["operation"] for t in detail["available_transitions"]}

        assert "procesar" not in offered
        # Archivar y cancelar siguen: los dos lo sacan de la vista pública.
        assert offered <= {"archivar", "cancelar"}

    def test_a_failed_report_can_still_be_archived_or_cancelled(self, processing):
        """La guarda no puede dejar varado un reporte que nunca se va a publicar.

        El archivado por inactividad (US-031) transiciona reportes *pendientes
        de validación*, que es justo donde queda uno cuyo difuminado falló. Sin
        esta excepción quedaría ahí para siempre, sin poder archivarse ni
        cancelarse. Los dos destinos lo sacan de la vista pública, así que no
        son una vía de publicación.
        """
        processing.photo_status = PhotoStatus.FALLIDA
        processing.photo_failed_at = timezone.now()
        processing.save(update_fields=["photo_status", "photo_failed_at"])

        apply_transition(
            processing,
            ARCHIVE_OPERATION,
            actor=Actor.SYSTEM,
            changed_by=None,
        )

        processing.refresh_from_db()
        assert processing.status == Report.Status.ARCHIVADO


class TestNoPathPublishesAnUnprocessedPhoto:
    """Escenario 6: la invariante se sostiene también fuera de la API."""

    def test_saving_a_photo_without_processing_it_is_rejected(self, processing):
        processing.photo = "reports/2026/09/colada.jpg"

        with pytest.raises(ValueError, match="US-042"):
            processing.save()

    def test_not_even_a_bulk_update_can_publish_it(self, processing):
        """`update()` no pasa por `save`: por eso la guarda vive también en la base."""
        with pytest.raises(IntegrityError), transaction.atomic():
            Report.objects.filter(pk=processing.pk).update(
                photo="reports/2026/09/colada.jpg",
            )


class TestVisibleOnceProcessed:
    """Escenario 1: al completarse, aparece donde tiene que aparecer."""

    def test_it_shows_up_everywhere_when_the_photo_is_ready(
        self,
        processing,
        neighbour_client,
    ):
        processing.photo = "reports/2026/09/difuminada.jpg"
        processing.photo_pending = ""
        processing.photo_status = PhotoStatus.PROCESADA
        processing.save()

        assert processing.pk in listed_ids(neighbour_client.get("/api/reports/"))
        assert processing.pk in listed_ids(neighbour_client.get("/api/reports/map/"))
        assert (
            neighbour_client.get(f"/api/reports/{processing.pk}/").status_code
            == HTTP_OK
        )
