"""Comando ``backfill_addresses``: completa la dirección de reportes viejos.

Los reportes creados por GPS antes de que existiera la geocodificación inversa
quedaron con ``address`` vacío y la búsqueda por zona (US-020) no los encontraba.
El comando corre una sola vez sobre esos casos.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory

COMMAND_PATH = "urbancheck.reports.management.commands.backfill_addresses"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """El comando duerme 1,1 s entre consultas por el límite de Nominatim."""
    monkeypatch.setattr(f"{COMMAND_PATH}.time.sleep", lambda _seconds: None)


def _run(**options) -> str:
    out = StringIO()
    call_command("backfill_addresses", stdout=out, **options)
    return out.getvalue()


@pytest.mark.django_db
class TestBackfillAddresses:
    def test_fills_reports_with_coordinates_only(self, monkeypatch):
        monkeypatch.setattr(
            f"{COMMAND_PATH}.reverse_geocode",
            lambda _lat, _lng: "Av. Sabattini 1200, Villa María",
        )
        report = ReportFactory.create(
            address="",
            latitude="-32.407",
            longitude="-63.240",
        )

        output = _run()

        report.refresh_from_db()
        assert report.address == "Av. Sabattini 1200, Villa María"
        assert "Resueltos 1 de 1" in output

    def test_ignores_reports_that_already_have_an_address(self, monkeypatch):
        monkeypatch.setattr(
            f"{COMMAND_PATH}.reverse_geocode", lambda _lat, _lng: "OTRA",
        )
        report = ReportFactory.create(address="Bv. España 250")

        _run()

        report.refresh_from_db()
        assert report.address == "Bv. España 250"

    def test_ignores_reports_without_coordinates(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            f"{COMMAND_PATH}.reverse_geocode",
            lambda lat, lng: calls.append((lat, lng)) or "X",
        )
        ReportFactory.create(address="", latitude=None, longitude=None)

        output = _run()

        assert calls == []
        assert "No hay reportes" in output

    def test_dry_run_does_not_save(self, monkeypatch):
        monkeypatch.setattr(
            f"{COMMAND_PATH}.reverse_geocode", lambda _lat, _lng: "Calle 1",
        )
        report = ReportFactory.create(address="", latitude="-32.4", longitude="-63.2")

        output = _run(dry_run=True)

        report.refresh_from_db()
        assert report.address == ""
        assert "dry-run" in output

    def test_a_failed_lookup_does_not_stop_the_rest(self, monkeypatch):
        """Nominatim puede no resolver una coordenada: el resto igual se completa."""
        resolved = ReportFactory.create(address="", latitude="-32.4", longitude="-63.2")
        failed = ReportFactory.create(address="", latitude="-32.5", longitude="-63.3")

        def fake(lat, _lng):
            return "Calle Resuelta 1" if str(lat) == "-32.400000" else ""

        monkeypatch.setattr(f"{COMMAND_PATH}.reverse_geocode", fake)

        output = _run()

        resolved.refresh_from_db()
        failed.refresh_from_db()
        assert resolved.address == "Calle Resuelta 1"
        assert failed.address == ""
        assert "Resueltos 1 de 2" in output
        assert "sin resultado" in output

    def test_backfilled_report_becomes_searchable_by_zone(self, monkeypatch):
        """El objetivo del comando: que US-020 encuentre esos reportes."""
        monkeypatch.setattr(
            f"{COMMAND_PATH}.reverse_geocode",
            lambda _lat, _lng: "Barrio Palermo, Villa María",
        )
        ReportFactory.create(address="", latitude="-32.4", longitude="-63.2")

        _run()

        found = Report.objects.filter(address__icontains="Palermo")
        assert found.count() == 1
