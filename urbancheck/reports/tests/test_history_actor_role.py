"""C-15: el historial registra con qué rol actuó quien cambió el estado.

El administrador de la plataforma ejecuta las acciones del panel con las
mismas reglas que el agente municipal (``Actor.MUNICIPAL_AGENT``). Decisión del
equipo (opción b): se mantiene, pero para auditoría cada asiento guarda el rol
real de quien lo hizo, tal como era en ese momento.
"""

import pytest
from rest_framework.test import APIClient

from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory

pytestmark = pytest.mark.django_db


def archive_as(user, report):
    client = APIClient()
    client.force_authenticate(user)
    return client.post(f"/api/panel/reports/{report.pk}/archive/")


def last_entry(report) -> ReportStatusHistory:
    return report.status_history.order_by("-created_at", "-pk").first()


def test_the_admin_is_recorded_as_admin():
    report = ReportFactory.create(status=Report.Status.EN_PROCESO)
    admin = PlatformAdminFactory.create()

    response = archive_as(admin, report)

    assert response.status_code == 200  # noqa: PLR2004
    entry = last_entry(report)
    assert entry.changed_by == admin
    assert entry.changed_by_role == User.Role.ADMIN_PLATAFORMA


def test_the_agent_is_recorded_as_agent():
    report = ReportFactory.create(status=Report.Status.EN_PROCESO)
    agent = MunicipalAgentFactory.create(municipality=report.municipality)

    archive_as(agent, report)

    assert last_entry(report).changed_by_role == User.Role.AGENTE_MUNICIPAL


def test_the_panel_shows_it_in_the_history():
    report = ReportFactory.create(status=Report.Status.EN_PROCESO)
    admin = PlatformAdminFactory.create()

    response = archive_as(admin, report)

    newest = max(response.data["status_history"], key=lambda e: e["created_at"])
    assert newest["changed_by_role"] == "admin_plataforma"


def test_the_role_is_frozen_at_the_time_of_the_change():
    report = ReportFactory.create(status=Report.Status.EN_PROCESO)
    agent = MunicipalAgentFactory.create(municipality=report.municipality)
    archive_as(agent, report)

    agent.role = User.Role.CIUDADANO
    agent.save(update_fields=["role"])

    assert last_entry(report).changed_by_role == User.Role.AGENTE_MUNICIPAL
