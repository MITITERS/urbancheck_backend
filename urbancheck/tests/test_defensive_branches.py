"""Ramas defensivas y de borde que las pruebas por endpoint no alcanzan.

Todo lo que hay acá se ejercita de rebote desde la API, pero solo por el camino
feliz. Son los casos que el código contempla explícitamente —un contexto sin
request, un municipio sin cobertura, una respuesta del catálogo vacía— y que sin
una prueba directa quedan como código que nadie ejecutó nunca.

Van juntos y no repartidos por app porque comparten la razón de existir, no el
módulo: cada uno cierra una decisión defensiva del Sprint 3.
"""

from __future__ import annotations

import pytest
import requests
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory

from urbancheck.municipalities import georef
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.notifications.models import Notification
from urbancheck.notifications.models import NotificationPreference
from urbancheck.reports import geocoding
from urbancheck.reports.api.permissions import CanDeleteComment
from urbancheck.reports.api.serializers import CommentSerializer
from urbancheck.reports.api.serializers import ReportListSerializer
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.reports.tests.factories import CommentFactory
from urbancheck.reports.tests.factories import LikeFactory
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.api.permissions import IsMunicipalAgent
from urbancheck.users.api.serializers import EMAIL_TAKEN_MESSAGE
from urbancheck.users.api.serializers import MunicipalAgentCreateSerializer
from urbancheck.users.api.serializers import PanelUserCreateSerializer
from urbancheck.users.forms import UserSignupForm
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory
from urbancheck.users.tests.factories import ValidatorFactory

pytestmark = pytest.mark.django_db


class TestSerializersWithoutRequest:
    """Los serializers se usan también fuera de una vista (comandos, señales)."""

    def test_can_delete_is_false_without_a_request_in_context(self):
        # Sin request no hay usuario contra el cual evaluar la autoría: negar es
        # el único default seguro.
        comment = CommentFactory.create()

        data = CommentSerializer(comment, context={}).data

        assert data["can_delete"] is False

    def test_is_liked_is_false_for_an_anonymous_reader(self):
        """El feed también se lee sin sesión: nadie anónimo tiene un like puesto."""
        report = ReportFactory.create()
        request = APIRequestFactory().get("/api/reports/")
        request.user = AnonymousUser()

        data = ReportListSerializer(report, context={"request": request}).data

        assert data["is_liked"] is False

    def test_is_liked_falls_back_to_a_query_when_the_annotation_is_missing(self):
        """Sin el respaldo, la respuesta saldría sin el campo y en silencio."""
        like = LikeFactory.create()
        request = APIRequestFactory().get("/api/reports/")
        request.user = like.user

        data = ReportListSerializer(like.report, context={"request": request}).data

        assert data["is_liked"] is True


class TestPermissionSafeMethods:
    """Los permisos de objeto dejan pasar la lectura y solo frenan la escritura."""

    def test_reading_a_comment_is_allowed_to_anyone(self):
        comment = CommentFactory.create()
        request = APIRequestFactory().get("/")
        request.user = UserFactory.create()

        assert CanDeleteComment().has_object_permission(request, None, comment)

    def test_a_stranger_cannot_delete_someone_elses_comment(self):
        comment = CommentFactory.create()
        request = APIRequestFactory().delete("/")
        request.user = UserFactory.create()

        assert not CanDeleteComment().has_object_permission(
            request,
            None,
            comment,
        )

    def test_the_panel_permission_refuses_a_validator(self):
        # El validador tiene cuenta de trabajo pero no opera el panel: es el
        # cruce de roles que la guarda existe para frenar.
        request = APIRequestFactory().get("/api/panel/reports/")
        request.user = ValidatorFactory.create()

        assert not IsMunicipalAgent().has_permission(request, None)

    def test_the_panel_permission_refuses_the_platform_admin_as_agent(self):
        request = APIRequestFactory().get("/api/panel/reports/")
        request.user = PlatformAdminFactory.create()

        assert not IsMunicipalAgent().has_permission(request, None)

    def test_the_panel_permission_accepts_an_enabled_agent(self):
        request = APIRequestFactory().get("/api/panel/reports/")
        request.user = MunicipalAgentFactory.create()

        assert IsMunicipalAgent().has_permission(request, None)


class TestCoveredBy:
    """El filtro por cobertura con un municipio que todavía no la definió."""

    def test_without_coverage_every_report_of_the_municipality_is_kept(self):
        # Un municipio sin límite trazado no puede descartar nada por
        # ubicación: filtrar ahí dejaría su bandeja vacía.
        municipality = MunicipalityFactory.create(
            latitude=None,
            longitude=None,
            boundary=None,
        )
        report = ReportFactory.create(municipality=municipality)

        assert report in Report.objects.covered_by(municipality)


class TestGeorefEdgeCases:
    """Bordes del catálogo oficial que el formulario tiene que sobrevivir."""

    def test_an_empty_province_list_falls_back_to_the_static_one(self, monkeypatch):
        """Georef contesta 200 con la lista vacía: es tan inservible como un corte."""

        class _Empty:
            def raise_for_status(self):
                return None

            def json(self):
                return {"provincias": []}

        monkeypatch.setattr(
            "urbancheck.municipalities.georef.requests.get",
            lambda *args, **kwargs: _Empty(),
        )

        assert georef.list_provinces() == georef.FALLBACK_PROVINCES

    def test_localities_without_a_province_do_not_hit_the_network(self, monkeypatch):
        def _explode(*args, **kwargs):
            msg = "no debería salir a la red"
            raise AssertionError(msg)

        monkeypatch.setattr("urbancheck.municipalities.georef.requests.get", _explode)

        assert georef.list_localities("") == []
        assert georef.list_localities(None) == []
        assert georef.list_localities("   ") == []

    def test_the_locality_list_is_served_from_the_cache_the_second_time(
        self,
        monkeypatch,
    ):
        calls = []

        class _Ok:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "localidades": [
                        {
                            "id": "14182060",
                            "nombre": "Bell Ville",
                            "centroide": {"lat": -32.63, "lon": -62.68},
                        },
                    ],
                }

        def fake_get(*args, **kwargs):
            calls.append(args)
            return _Ok()

        monkeypatch.setattr("urbancheck.municipalities.georef.requests.get", fake_get)
        cache.clear()

        first = georef.list_localities("14")
        second = georef.list_localities("14")

        assert first == second
        assert len(calls) == 1


class TestGeocodingMalformedPayload:
    """Nominatim devuelve resultados heterogéneos: uno roto no rompe la búsqueda."""

    def test_a_result_without_coordinates_is_skipped(self, monkeypatch):
        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return [
                    {"display_name": "Sin lat", "lon": "-63.2"},
                    {"display_name": "Roto", "lat": "no-es-un-numero", "lon": "-63.2"},
                    {"display_name": "Bueno", "lat": "-32.41", "lon": "-63.24"},
                ]

        monkeypatch.setattr(
            "urbancheck.reports.geocoding.requests.get",
            lambda *args, **kwargs: _Response(),
        )
        cache.clear()

        results = geocoding.search_addresses("Villa María")

        assert [r["display_name"] for r in results] == ["Bueno"]

    def test_a_network_error_returns_no_results(self, monkeypatch):
        def _explode(*args, **kwargs):
            raise requests.RequestException

        monkeypatch.setattr("urbancheck.reports.geocoding.requests.get", _explode)
        cache.clear()

        assert geocoding.search_addresses("Villa María") == []


class TestStringRepresentations:
    """Los ``__str__`` son lo que se lee en el admin y en los logs de un incidente."""

    def test_a_municipality_reads_as_city_and_province(self):
        municipality = MunicipalityFactory.create(
            city="Villa María",
            province="Córdoba",
        )

        assert str(municipality) == "Villa María (Córdoba)"

    def test_a_status_history_entry_shows_the_transition(self):
        report = ReportFactory.create()
        entry = ReportStatusHistory.objects.create(
            report=report,
            previous_status=Report.Status.REPORTADO,
            status=Report.Status.EN_PROCESO,
        )

        assert str(entry) == f"{report.pk}: reportado → en_proceso"

    def test_the_initial_entry_shows_a_dash_instead_of_an_empty_status(self):
        report = ReportFactory.create()
        entry = ReportStatusHistory.objects.create(
            report=report,
            previous_status="",
            status=Report.Status.PENDIENTE_VALIDACION,
        )

        assert str(entry) == f"{report.pk}: — → pendiente_validacion"

    def test_a_notification_preference_reads_as_user_kind_and_value(self):
        user = UserFactory.create()
        preference = NotificationPreference.objects.create(
            user=user,
            kind=Notification.Kind.CAMBIO_ESTADO,
            enabled=False,
        )

        assert str(preference) == f"{user}: {Notification.Kind.CAMBIO_ESTADO} = False"


class TestPanelUserCreateSerializer:
    """La base compartida por el alta de agentes (US-017) y la de validadores."""

    def test_a_taken_email_is_refused_case_insensitively(self):
        # El correo es el identificador de la cuenta: dos altas con el mismo
        # correo dejarían a una de las dos sin poder ingresar.
        UserFactory.create(email="ana@villamaria.gob.ar")
        serializer = MunicipalAgentCreateSerializer(
            data={
                "name": "Ana Agente",
                "email": "ANA@VillaMaria.GOB.AR",
                "temporary_password": "Provisoria2026!",
                "municipality_id": MunicipalityFactory.create().pk,
            },
        )

        assert not serializer.is_valid()
        assert EMAIL_TAKEN_MESSAGE in serializer.errors["email"][0]

    def test_the_base_class_refuses_to_guess_the_municipality(self):
        """Cada subclase decide de dónde sale la jurisdicción.

        La base no puede tener un default: derivarla de la del creador y
        elegirla en el body son dos reglas distintas, y equivocarse da de alta
        una cuenta en el municipio equivocado.
        """
        with pytest.raises(NotImplementedError):
            PanelUserCreateSerializer().get_municipality()


class TestSignupForm:
    """El alta del vecino desde la app: el nombre es parte del registro."""

    def test_it_stores_the_name_given_at_signup(self, rf):
        request = rf.post("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        form = UserSignupForm(
            data={
                "email": "vecina@example.com",
                "name": "Vecina del Centro",
                "password1": "Contrasena2026!",
                "password2": "Contrasena2026!",
            },
        )

        assert form.is_valid(), form.errors
        user = form.save(request)

        user.refresh_from_db()
        assert user.name == "Vecina del Centro"


class TestScopingWithoutCoordinates:
    """El acotado por ubicación es opt-in: sin coordenadas nada cambia (US-034)."""

    def test_the_feed_without_coordinates_is_not_scoped(self):
        # Es lo que mantiene andando a un cliente viejo que todavía no manda la
        # posición.
        citizen = UserFactory.create()
        report = ReportFactory.create()
        client = APIClient()
        client.force_authenticate(citizen)

        response = client.get("/api/reports/")

        assert response.status_code == 200
        assert report.pk in {item["id"] for item in response.data["results"]}

    def test_my_own_reports_are_never_scoped_by_where_i_am(self):
        """Los propios se ven esté donde esté el vecino."""
        citizen = UserFactory.create()
        report = ReportFactory.create(author=citizen)
        client = APIClient()
        client.force_authenticate(citizen)

        response = client.get(
            "/api/reports/?mine=true&latitude=-34.6&longitude=-58.4",
        )

        assert response.status_code == 200
        assert report.pk in {item["id"] for item in response.data["results"]}


class TestValidationWithoutReportCoordinates:
    """Un reporte sin coordenadas no tiene contra qué medir la distancia."""

    def test_it_can_be_validated_from_anywhere(self):
        # Sin punto del problema no hay "estar en el lugar" que exigir: pedirlo
        # igual dejaría el reporte trabado para siempre.
        municipality = MunicipalityFactory.create()
        validator = ValidatorFactory.create(municipality=municipality)
        report = ReportFactory.create(
            municipality=municipality,
            status=Report.Status.PENDIENTE_VALIDACION,
            latitude=None,
            longitude=None,
        )
        client = APIClient()
        client.force_authenticate(validator)

        response = client.post(
            f"/api/validation/reports/{report.pk}/validate/",
            {"latitude": -34.6037, "longitude": -58.3816},
            format="json",
        )

        assert response.status_code == 200
        report.refresh_from_db()
        assert report.status == Report.Status.REPORTADO
