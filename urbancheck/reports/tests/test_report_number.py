"""El reporte se numera dentro de su municipalidad, no de forma global.

Es como lo nombran el vecino y el municipio: «el reporte 12 de Villa María». El
``id`` de la base sigue siendo la clave técnica y es lo que viaja en las URLs;
``number`` es el identificador de cara al usuario.
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from PIL import Image
from rest_framework.test import APIClient

from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestNumberingIsPerMunicipality:
    def test_each_municipality_starts_at_one(self):
        one, other = MunicipalityFactory.create(), MunicipalityFactory.create()

        first_of_one = ReportFactory.create(municipality=one)
        first_of_other = ReportFactory.create(municipality=other)

        assert first_of_one.number == 1
        assert first_of_other.number == 1

    def test_it_counts_up_within_the_municipality(self):
        municipality = MunicipalityFactory.create()

        numbers = [
            ReportFactory.create(municipality=municipality).number for _ in range(3)
        ]

        assert numbers == [1, 2, 3]

    def test_the_other_municipality_does_not_advance_the_count(self):
        """Es lo que distingue esto de un contador global."""
        one, other = MunicipalityFactory.create(), MunicipalityFactory.create()
        ReportFactory.create(municipality=one)

        ReportFactory.create(municipality=other)
        ReportFactory.create(municipality=other)
        second_of_one = ReportFactory.create(municipality=one)

        assert second_of_one.number == 2

    def test_the_number_is_not_the_id(self):
        one, other = MunicipalityFactory.create(), MunicipalityFactory.create()
        ReportFactory.create(municipality=one)
        report = ReportFactory.create(municipality=other)

        assert report.number == 1
        assert report.id != report.number


class TestTheNumberIsStable:
    def test_it_does_not_change_when_the_report_is_edited(self):
        report = ReportFactory.create()
        original = report.number

        report.description = "Otra descripción"
        report.save()

        report.refresh_from_db()
        assert report.number == original

    def test_a_number_in_the_middle_is_never_reused(self):
        """Borrar uno del medio no corre a los demás ni recicla su número."""
        municipality = MunicipalityFactory.create()
        first = ReportFactory.create(municipality=municipality)
        second = ReportFactory.create(municipality=municipality)
        third = ReportFactory.create(municipality=municipality)

        second.delete()
        fourth = ReportFactory.create(municipality=municipality)

        third.refresh_from_db()
        assert first.number == 1
        assert third.number == 3
        assert fourth.number == 4

    def test_the_last_number_is_reissued_if_that_report_is_deleted(self):
        """Consecuencia asumida de derivar la secuencia del máximo.

        Solo alcanza al reporte más reciente del municipio, y solo su autor
        puede borrarlo mientras el municipio todavía no lo tomó. Se prueba para
        que el día que se decida cambiarlo, el test diga qué se está cambiando.
        """
        municipality = MunicipalityFactory.create()
        ReportFactory.create(municipality=municipality)
        last = ReportFactory.create(municipality=municipality)
        assert last.number == 2

        last.delete()

        assert ReportFactory.create(municipality=municipality).number == 2

    def test_two_reports_cannot_share_a_number_in_the_same_municipality(self):
        municipality = MunicipalityFactory.create()
        first = ReportFactory.create(municipality=municipality)
        other = ReportFactory.create(municipality=municipality)

        other.number = first.number
        with pytest.raises(IntegrityError):
            other.save()


class TestTheNumberTravelsToTheClients:
    @pytest.fixture
    def client(self):
        api = APIClient()
        api.force_authenticate(UserFactory.create())
        return api

    def test_the_feed_carries_it(self, client):
        report = ReportFactory.create(status=Report.Status.REPORTADO)

        response = client.get("/api/reports/")

        row = next(r for r in response.data["results"] if r["id"] == report.id)
        assert row["number"] == report.number

    def test_the_detail_carries_it(self, client):
        report = ReportFactory.create(status=Report.Status.REPORTADO)

        response = client.get(f"/api/reports/{report.id}/")

        assert response.data["number"] == report.number

    def test_the_map_carries_it(self, client):
        """El popup del mapa nombra el reporte por su número."""
        report = ReportFactory.create(status=Report.Status.REPORTADO)

        response = client.get("/api/reports/map/")

        marker = next(m for m in response.data["results"] if m["id"] == report.id)
        assert marker["number"] == report.number

    def test_a_new_report_comes_back_numbered(self, client):
        """El alta responde con el número ya asignado, sin pedir el detalle."""
        buf = io.BytesIO()
        Image.new("RGB", (60, 60), (10, 10, 10)).save(buf, format="JPEG")
        buf.seek(0)

        response = client.post(
            "/api/reports/",
            data={
                "photo": SimpleUploadedFile(
                    "s.jpg",
                    buf.read(),
                    content_type="image/jpeg",
                ),
                "description": "Un bache",
                "category": "bache",
                "latitude": "-32.4",
                "longitude": "-63.24",
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert response.data["number"] is not None
        assert response.data["number"] == Report.objects.get(
            pk=response.data["id"],
        ).number

    def test_the_client_cannot_choose_it(self, client):
        """Es del servidor: si el cliente lo propone, se ignora."""
        report = ReportFactory.create(author=UserFactory.create())

        response = client.patch(
            f"/api/reports/{report.id}/",
            {"number": 999},
            format="json",
        )

        report.refresh_from_db()
        assert report.number != 999
        assert response.status_code in {200, 403}
