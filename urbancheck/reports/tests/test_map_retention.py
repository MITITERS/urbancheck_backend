"""Los reportes resueltos dejan de dibujarse en el mapa a los quince días.

El mapa responde «¿qué pasa hoy?»; el feed es el registro. Por eso la regla es
de **qué se dibuja** y no de qué existe: el mismo reporte que sale del mapa
sigue entero en el feed, en su detalle y en el panel.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

MAP_URL = "/api/reports/map/"
FEED_URL = "/api/reports/"

HTTP_OK = 200
RETENTION_DAYS = 15


@pytest.fixture
def client():
    api = APIClient()
    api.force_authenticate(UserFactory.create())
    return api


def ids_on_map(response):
    return {row["id"] for row in response.data["results"]}


def ids_on_feed(response):
    return {row["id"] for row in response.data["results"]}


def resolved(days_ago: float, *, status=Report.Status.RESUELTO):
    """Un reporte con coordenadas que llegó a *Resuelto* hace ``days_ago`` días.

    ``with_history=False`` apaga el asiento que arma la fábrica: lo crea con la
    fecha de hoy, y como la regla mira el asiento **más reciente**, ese tapaba
    al que este helper fecha en el pasado y ningún reporte llegaba a vencer.
    """
    report = ReportFactory.create(
        status=status,
        latitude="-32.410300",
        longitude="-63.240000",
        with_history=False,
    )
    entry = ReportStatusHistory.objects.create(
        report=report,
        previous_status=Report.Status.RESUELTO_PENDIENTE,
        status=Report.Status.RESUELTO,
    )
    # ``created_at`` es ``auto_now_add``: la única forma de fecharlo en el
    # pasado es actualizarlo después de creado.
    ReportStatusHistory.objects.filter(pk=entry.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago),
    )
    return report


class TestMapRetention:
    def test_a_recently_resolved_report_is_still_drawn(self, client):
        report = resolved(days_ago=RETENTION_DAYS - 1)

        assert report.pk in ids_on_map(client.get(MAP_URL))

    def test_one_resolved_longer_ago_disappears(self, client):
        report = resolved(days_ago=RETENTION_DAYS + 1)

        assert report.pk not in ids_on_map(client.get(MAP_URL))

    def test_but_it_stays_in_the_feed(self, client):
        """La razón de ser de la regla: sale del mapa y de ningún lado más."""
        report = resolved(days_ago=RETENTION_DAYS + 30)

        assert report.pk in ids_on_feed(client.get(FEED_URL))

    def test_and_its_detail_still_opens(self, client):
        report = resolved(days_ago=RETENTION_DAYS + 30)

        assert client.get(f"/api/reports/{report.pk}/").status_code == HTTP_OK

    def test_and_the_panel_still_lists_it(self):
        """El municipio gestiona; no se le esconde su propio historial."""
        report = resolved(days_ago=RETENTION_DAYS + 30)
        agent = MunicipalAgentFactory.create(municipality=report.municipality)
        panel = APIClient()
        panel.force_authenticate(agent)

        listed = {row["id"] for row in panel.get("/api/panel/reports/").data["results"]}
        assert report.pk in listed

    def test_it_only_touches_resolved_reports(self, client):
        """Escenario del pedido: «solo los de ese estado».

        Uno *En proceso* viejo sigue siendo un problema abierto, y el mapa es
        justamente donde tiene que verse.
        """
        old = resolved(
            days_ago=RETENTION_DAYS + 90,
            status=Report.Status.EN_PROCESO,
        )

        assert old.pk in ids_on_map(client.get(MAP_URL))

    def test_pending_confirmation_is_not_hidden(self, client):
        """Mientras corre la ventana de objeción el caso sigue abierto.

        Esconderlo del mapa justo cuando el vecino puede querer revisarlo sería
        esconderle lo que tiene que decidir.
        """
        report = resolved(
            days_ago=RETENTION_DAYS + 30,
            status=Report.Status.RESUELTO_PENDIENTE,
        )

        assert report.pk in ids_on_map(client.get(MAP_URL))

    def test_a_resolved_report_without_history_stays_drawn(self, client):
        """Ante la duda se muestra de más, no se esconde de menos.

        No debería pasar —toda transición deja asiento—, pero si pasara, el
        reporte no puede desaparecer sin que nadie sepa por qué.
        """
        report = ReportFactory.create(
            status=Report.Status.RESUELTO,
            latitude="-32.410300",
            longitude="-63.240000",
            with_history=False,
        )

        assert report.pk in ids_on_map(client.get(MAP_URL))

    def test_the_window_is_read_from_configuration(self, client, settings):
        """Se puede bajar sin redeploy, como el resto de los plazos."""
        report = resolved(days_ago=1)

        settings.MAP_RESOLVED_RETENTION_MINUTES = 10

        assert report.pk not in ids_on_map(client.get(MAP_URL))

    def test_no_row_is_duplicated_by_the_lookup(self, client):
        """El recorte va por subconsulta: no puede multiplicar marcadores."""
        report = resolved(days_ago=1)
        ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.RESUELTO_PENDIENTE,
            status=Report.Status.RESUELTO,
        )

        markers = client.get(MAP_URL).data["results"]

        assert [row["id"] for row in markers].count(report.pk) == 1
