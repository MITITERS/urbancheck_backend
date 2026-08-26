"""Solo el vecino participa: reportar, comentar y dar me gusta.

Las cuentas de trabajo operan el circuito: el validador verifica en terreno lo
que reportan los vecinos, el agente lo gestiona desde el panel y el
administrador opera la plataforma. Un aporte propio los pondría de los dos lados
del mismo caso. La regla es del rol y no del estado de la cuenta: el validador
dado de baja sigue sin participar, aunque ya no pueda validar.

Leer no está alcanzado, y es la mitad importante del contrato: el personal
municipal sigue viendo el feed, el mapa, el detalle y los comentarios de su
jurisdicción.
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.reports.api.permissions import CANNOT_PARTICIPATE_MESSAGE
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db


def make_image_file(name="test.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color=(100, 100, 100)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


def post_report(client):
    return client.post(
        "/api/reports/",
        data={
            "photo": make_image_file(),
            "description": "Hay un bache enorme",
            "category": "bache",
            "latitude": "-34.6",
            "longitude": "-58.4",
        },
        format="multipart",
    )


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


WORK_ACCOUNT_FACTORIES = [
    ValidatorFactory,
    MunicipalAgentFactory,
    PlatformAdminFactory,
]


class TestParticipatesAsCitizenRule:
    @pytest.mark.parametrize("factory", WORK_ACCOUNT_FACTORIES)
    def test_the_work_accounts_cannot(self, factory):
        assert factory.create().participates_as_citizen is False

    def test_a_deactivated_validator_still_cannot(self):
        """La baja lógica quita validar, no devuelve reportar."""
        validator = ValidatorFactory.create(is_validator_active=False)
        assert validator.can_validate is False
        assert validator.participates_as_citizen is False

    def test_only_the_citizen_can(self):
        assert UserFactory.create().participates_as_citizen is True

    def test_the_rule_is_the_complement_of_citizen(self):
        """Si mañana se agrega un rol, tiene que caer de un lado explícito."""
        assert User.WORK_ROLES == set(User.Role.values) - {User.Role.CIUDADANO}


class TestWorkAccountsCannotCreateReports:
    @pytest.mark.parametrize("factory", WORK_ACCOUNT_FACTORIES)
    def test_the_request_is_rejected(self, factory):
        response = post_report(client_for(factory.create()))

        assert response.status_code == 403
        assert response.data["detail"] == CANNOT_PARTICIPATE_MESSAGE

    @pytest.mark.parametrize("factory", WORK_ACCOUNT_FACTORIES)
    def test_nothing_is_persisted(self, factory):
        post_report(client_for(factory.create()))

        assert Report.objects.count() == 0

    def test_a_deactivated_validator_is_rejected_too(self):
        validator = ValidatorFactory.create(is_validator_active=False)

        assert post_report(client_for(validator)).status_code == 403

    def test_the_citizen_is_untouched(self):
        assert post_report(client_for(UserFactory.create())).status_code == 201


MUNICIPAL_STAFF = [ValidatorFactory, MunicipalAgentFactory]


def report_in(user):
    """Un reporte de la jurisdicción de la cuenta, para que le sea visible."""
    return ReportFactory.create(
        municipality=user.municipality,
        status=Report.Status.REPORTADO,
    )


class TestWorkAccountsCannotComment:
    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_the_comment_is_rejected(self, factory):
        """El municipio responde por el estado del reporte, no comentando."""
        user = factory.create(must_change_password=False)
        report = report_in(user)

        response = client_for(user).post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Paso a verificarlo"},
            format="json",
        )

        assert response.status_code == 403
        assert response.data["detail"] == CANNOT_PARTICIPATE_MESSAGE

    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_nothing_is_persisted(self, factory):
        user = factory.create(must_change_password=False)
        report = report_in(user)

        client_for(user).post(
            f"/api/reports/{report.id}/comments/",
            data={"text": "Paso a verificarlo"},
            format="json",
        )

        assert report.comments.count() == 0


class TestWorkAccountsCannotLike:
    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_the_like_is_rejected(self, factory):
        user = factory.create(must_change_password=False)
        report = report_in(user)

        response = client_for(user).post(f"/api/reports/{report.id}/like/")

        assert response.status_code == 403
        assert report.likes.count() == 0

    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_an_older_like_can_still_be_removed(self, factory):
        """Bloquear el DELETE dejaría trabado un me gusta previo a esta regla."""
        user = factory.create(must_change_password=False)
        report = report_in(user)
        Like.objects.create(report=report, user=user)

        response = client_for(user).delete(f"/api/reports/{report.id}/like/")

        assert response.status_code == 200
        assert report.likes.count() == 0


class TestReadingIsUntouched:
    """Se saca aportar, no mirar: el municipio tiene que poder leer."""

    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_it_still_reads_the_feed(self, factory):
        user = factory.create(must_change_password=False)
        report_in(user)

        response = client_for(user).get("/api/reports/")

        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_it_still_reads_the_detail(self, factory):
        user = factory.create(must_change_password=False)
        report = report_in(user)

        assert client_for(user).get(f"/api/reports/{report.id}/").status_code == 200

    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_it_still_reads_the_comments_of_the_neighbours(self, factory):
        user = factory.create(must_change_password=False)
        report = report_in(user)
        CommentFactory.create(report=report, text="Sigue igual")

        response = client_for(user).get(f"/api/reports/{report.id}/comments/")

        assert response.status_code == 200
        assert [row["text"] for row in response.data] == ["Sigue igual"]

    @pytest.mark.parametrize("factory", MUNICIPAL_STAFF)
    def test_it_still_reads_the_map(self, factory):
        user = factory.create(must_change_password=False)
        report_in(user)

        assert client_for(user).get("/api/reports/map/").status_code == 200
