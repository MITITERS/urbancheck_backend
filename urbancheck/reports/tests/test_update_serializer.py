"""Serializers del Sprint 2: edición (US-018), ``can_edit`` (US-018/US-019) y el
payload del mapa (US-010).

Se prueban aislados del viewset porque son el contrato que consume la app: qué
campos acepta la edición, qué campos ignora, y qué mínimo necesita el mapa para
dibujar un marcador con su popup.
"""

from __future__ import annotations

import pytest
from django.db.models import Count
from rest_framework.test import APIRequestFactory

from urbancheck.reports.api.serializers import ReportDetailSerializer
from urbancheck.reports.api.serializers import ReportMapSerializer
from urbancheck.reports.api.serializers import ReportUpdateSerializer
from urbancheck.reports.models import Report
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.tests.factories import UserFactory


def _request(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
class TestReportUpdateSerializer:
    def test_accepts_description_and_category(self):
        report = ReportFactory.create(category=Report.Category.BACHE)
        serializer = ReportUpdateSerializer(
            report,
            data={"description": "Ahora es más grande", "category": "vereda"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.description == "Ahora es más grande"
        assert updated.category == Report.Category.VEREDA

    def test_rejects_an_empty_description(self):
        report = ReportFactory.create()
        serializer = ReportUpdateSerializer(
            report, data={"description": ""}, partial=True,
        )
        assert not serializer.is_valid()
        assert "description" in serializer.errors

    def test_rejects_a_whitespace_only_description(self):
        """Se rechaza, y el mensaje lo pone DRF.

        ``CharField`` recorta los espacios antes de validar, así que "   " llega
        como "" y salta el error ``blank`` estándar. El serializer tuvo un
        ``validate_description`` propio para esto: era inalcanzable por la misma
        razón y se retiró en el Sprint 3.
        """
        report = ReportFactory.create()
        serializer = ReportUpdateSerializer(
            report,
            data={"description": "   "},
            partial=True,
        )
        assert not serializer.is_valid()
        assert "description" in serializer.errors

    def test_rejects_an_invalid_category(self):
        report = ReportFactory.create()
        serializer = ReportUpdateSerializer(
            report,
            data={"category": "meteorito"},
            partial=True,
        )
        assert not serializer.is_valid()
        assert "category" in serializer.errors

    def test_location_is_not_editable(self):
        """Moverlo lo convertiría en otro reporte y rompería el historial."""
        report = ReportFactory.create(latitude="-32.400000", longitude="-63.240000")
        serializer = ReportUpdateSerializer(
            report,
            data={"latitude": "0.000000", "longitude": "0.000000", "description": "x"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert str(updated.latitude) == "-32.400000"
        assert str(updated.longitude) == "-63.240000"

    def test_status_is_not_editable_by_the_author(self):
        """El estado lo gobierna el municipio, no el ciudadano."""
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        serializer = ReportUpdateSerializer(
            report,
            data={"status": "resuelto", "description": "x"},
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().status == Report.Status.REPORTADO

    def test_edited_at_is_read_only(self):
        """Lo sella el viewset; el cliente no puede falsearlo."""
        assert "edited_at" in ReportUpdateSerializer.Meta.read_only_fields


@pytest.mark.django_db
class TestCanEdit:
    def test_true_for_the_author_of_an_editable_report(self):
        author = UserFactory.create()
        report = ReportFactory.create(
            author=author, status=Report.Status.PENDIENTE_VALIDACION
        )
        data = ReportDetailSerializer(
            report, context={"request": _request(author)},
        ).data
        assert data["can_edit"] is True

    def test_false_for_the_author_once_it_is_validated(self):
        author = UserFactory.create()
        report = ReportFactory.create(author=author, status=Report.Status.EN_PROCESO)
        data = ReportDetailSerializer(
            report, context={"request": _request(author)},
        ).data
        assert data["can_edit"] is False

    def test_false_for_another_user(self):
        report = ReportFactory.create(status=Report.Status.REPORTADO)
        other = UserFactory.create()
        data = ReportDetailSerializer(report, context={"request": _request(other)}).data
        assert data["can_edit"] is False


@pytest.mark.django_db
class TestReportMapSerializer:
    def _annotated(self, report):
        """Como ``ReportViewSet.get_queryset``: el mapa siempre anota el contador."""
        return Report.objects.annotate(like_count=Count("likes", distinct=True)).get(
            pk=report.pk,
        )

    def test_carries_what_the_marker_and_popup_need(self):
        report = ReportFactory.create(
            latitude="-32.407",
            longitude="-63.240",
            address="Sabattini 1200",
        )
        instance = self._annotated(report)
        data = ReportMapSerializer(
            instance, context={"request": _request(report.author)},
        ).data
        assert set(data) == {
            "id",
            # El popup lo nombra por su número de municipio, no por el id.
            "number",
            "photo",
            "category",
            "status",
            "latitude",
            "longitude",
            "address",
            "like_count",
        }

    def test_does_not_carry_the_description(self):
        """Payload mínimo: el mapa trae todos los marcadores de una sola vez."""
        report = ReportFactory.create(description="Texto largo que no viaja al mapa")
        instance = self._annotated(report)
        data = ReportMapSerializer(
            instance, context={"request": _request(report.author)},
        ).data
        assert "description" not in data
        assert "comments" not in data

    @pytest.mark.xfail(
        reason=(
            "OBS-01: like_count es un campo declarativo read_only alimentado por la "
            "anotación del queryset. Sin ella DRF lo omite del JSON en silencio, "
            "la misma trampa que se resolvió para is_liked en §7 del sprint. Hoy no "
            "afecta al usuario porque el endpoint del mapa siempre anota."
        ),
        strict=False,
    )
    def test_like_count_survives_without_the_annotation(self):
        report = ReportFactory.create()
        data = ReportMapSerializer(
            report, context={"request": _request(report.author)},
        ).data
        assert "like_count" in data
