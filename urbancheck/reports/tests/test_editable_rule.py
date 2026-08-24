"""US-018 y US-019: la regla de estados editables, a nivel modelo.

La regla vive en ``Report.EDITABLE_STATUSES`` y la consumen tanto el viewset
(``perform_update`` / ``perform_destroy``) como el serializer (``can_edit``). Se
prueba acá de forma aislada para que un cambio en la lista de estados falle en un
único lugar y no solo de rebote en los tests de la API.
"""

from __future__ import annotations

import pytest

from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory

EDITABLE = [Report.Status.PENDIENTE_VALIDACION, Report.Status.REPORTADO]
BLOCKED = [
    Report.Status.EN_PROCESO,
    Report.Status.RESUELTO,
    Report.Status.CANCELADO,
    Report.Status.ARCHIVADO,
]


@pytest.mark.django_db
class TestIsEditable:
    @pytest.mark.parametrize("status", EDITABLE)
    def test_editable_before_management(self, status):
        report = ReportFactory.create(status=status)
        assert report.is_editable is True

    @pytest.mark.parametrize("status", BLOCKED)
    def test_not_editable_once_in_management(self, status):
        report = ReportFactory.create(status=status)
        assert report.is_editable is False

    def test_every_status_is_classified(self):
        """Un estado nuevo obliga a decidir explícitamente si es editable."""
        assert set(EDITABLE) | set(BLOCKED) == set(Report.Status.values)

    def test_editable_statuses_is_immutable(self):
        """Es un frozenset: nadie puede ampliar la regla en runtime."""
        assert isinstance(Report.EDITABLE_STATUSES, frozenset)
        with pytest.raises(AttributeError):
            Report.EDITABLE_STATUSES.add(Report.Status.EN_PROCESO)


@pytest.mark.django_db
class TestEditedAt:
    def test_starts_empty(self):
        """Un reporte recién creado no está editado: no debe decir "editado el…"."""
        report = ReportFactory.create()
        assert report.edited_at is None

    def test_is_independent_from_updated_at(self):
        """``updated_at`` se mueve con cualquier guardado; ``edited_at`` no.

        Por eso existen los dos campos: un cambio de estado hecho por el municipio
        no debe hacer que el reporte figure como editado por el ciudadano.
        """
        report = ReportFactory.create()
        report.status = Report.Status.EN_PROCESO
        report.save(update_fields=["status", "updated_at"])
        report.refresh_from_db()
        assert report.updated_at is not None
        assert report.edited_at is None
