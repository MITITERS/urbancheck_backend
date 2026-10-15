"""Registro de eventos de seguridad (Sprint 5, punto 5.5).

Cada evento lleva usuario, IP y ruta; ninguno lleva contraseñas, tokens ni
cuerpos de solicitud.
"""

from __future__ import annotations

import json
import logging

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client
from rest_framework.test import APIClient

from urbancheck.common.security import log_event
from urbancheck.common.security_receivers import account_fingerprint
from urbancheck.municipalities.tests.factories import MunicipalityFactory
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.users.models import User
from urbancheck.users.tests.factories import MunicipalAgentFactory
from urbancheck.users.tests.factories import PlatformAdminFactory
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/_allauth/app/v1/auth/login"
PASSWORD_CHANGE_URL = "/_allauth/app/v1/account/password/change"  # noqa: S105
PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105


def post_json(client, url, data, **headers):
    return client.post(
        url,
        json.dumps(data),
        content_type="application/json",
        **headers,
    )


@pytest.fixture
def security_log(caplog):
    caplog.set_level(logging.INFO, logger="security")

    def events():
        return [
            record.security
            for record in caplog.records
            if record.name == "security" and hasattr(record, "security")
        ]

    return events


def by_event(events, name):
    return [event for event in events if event["event"] == name]


@pytest.fixture
def account():
    user = UserFactory.create(email="vecina@example.com")
    user.set_password(PASSWORD)
    user.save()
    return user


def assert_no_secrets(caplog, *secrets):
    text = "\n".join(record.getMessage() for record in caplog.records)
    for secret in secrets:
        assert secret not in text


class TestLogins:
    def test_a_successful_login_is_logged_with_user_ip_and_path(
        self,
        account,
        security_log,
        caplog,
    ):
        """CP-SEC18-01: login exitoso, con usuario, IP y ruta; sin el token."""
        response = post_json(
            Client(),
            LOGIN_URL,
            {"email": account.email, "password": PASSWORD},
        )
        token = response.json()["meta"]["session_token"]

        [event] = by_event(security_log(), "login_succeeded")
        assert event["user_id"] == account.pk
        assert event["ip"] == "127.0.0.1"
        assert event["path"] == LOGIN_URL
        assert_no_secrets(caplog, PASSWORD, token)

    def test_a_failed_login_is_logged_without_the_password(
        self,
        account,
        security_log,
        caplog,
    ):
        """CP-SEC18-02: login fallido, con la huella de la cuenta y sin lo escrito."""
        post_json(
            Client(),
            LOGIN_URL,
            {"email": account.email, "password": "ContraseñaIncorrecta1"},
        )

        [event] = by_event(security_log(), "login_failed")
        assert event["user_id"] is None
        assert event["ip"] == "127.0.0.1"
        assert event["account"] == account_fingerprint(account.email)
        assert_no_secrets(caplog, "ContraseñaIncorrecta1", account.email)

    def test_a_lockout_is_logged(self, account, security_log):
        """CP-SEC18-03: el bloqueo por intentos queda registrado como 429."""
        client = Client()
        for _ in range(6):
            post_json(client, LOGIN_URL, {"email": account.email, "password": "x"})

        events = security_log()
        assert len(by_event(events, "login_locked")) == 1
        assert len(by_event(events, "http_429")) == 1


class TestPasswords:
    def test_a_password_change_is_logged(self, account, security_log, caplog):
        """CP-SEC18-04: cambio de contraseña, sin la vieja ni la nueva."""
        client = Client()
        login = post_json(
            client,
            LOGIN_URL,
            {"email": account.email, "password": PASSWORD},
        )
        token = login.json()["meta"]["session_token"]

        post_json(
            client,
            PASSWORD_CHANGE_URL,
            {"current_password": PASSWORD, "new_password": "Nueva#Clave2026"},
            HTTP_X_SESSION_TOKEN=token,
        )

        [event] = by_event(security_log(), "password_changed")
        assert event["user_id"] == account.pk
        assert_no_secrets(caplog, PASSWORD, "Nueva#Clave2026", token)


class TestWorkAccounts:
    def test_creating_an_agent_from_the_panel_is_logged(self, security_log, caplog):
        """CP-SEC18-05: alta de agente, con quién la hizo y la cuenta creada."""
        admin = PlatformAdminFactory.create()
        client = APIClient()
        client.force_authenticate(admin)
        municipality = MunicipalAgentFactory.create().municipality

        response = client.post(
            "/api/municipal-agents/",
            {
                "email": "agente@example.com",
                "name": "Agente Nuevo",
                "municipality_id": municipality.pk,
                "temporary_password": "Temporal#2026x",
            },
            format="json",
        )

        assert response.status_code == 201, response.data  # noqa: PLR2004
        [event] = [
            e
            for e in by_event(security_log(), "work_account_created")
            if e["account"] == response.data["id"]
        ]
        assert event["user_id"] == admin.pk
        assert event["role"] == User.Role.AGENTE_MUNICIPAL
        assert event["path"] == "/api/municipal-agents/"
        assert_no_secrets(caplog, "Temporal#2026x")

    def test_a_citizen_signup_is_not_a_work_account(self, security_log):
        """CP-SEC18-06: un vecino que se registra no figura como alta de trabajo."""
        UserFactory.create()

        assert by_event(security_log(), "work_account_created") == []

    def test_creating_a_municipality_is_logged(self, security_log):
        """CP-SEC18-07: alta de municipalidad."""
        municipality = MunicipalityFactory.create()

        assert any(
            event["municipality"] == municipality.pk
            for event in by_event(security_log(), "municipality_created")
        )


class TestComplaints:
    def test_a_complaint_is_logged_with_user_and_ip(self, security_log):
        """CP-SEC18-08: denuncia de contenido, con usuario e IP."""
        neighbour = UserFactory.create()
        report = ReportFactory.create()
        client = APIClient(REMOTE_ADDR="203.0.113.9")
        client.force_authenticate(neighbour)

        client.post(
            f"/api/reports/{report.pk}/complaints/",
            {"reason": ReportComplaint.Reason.REPORTE_FALSO, "comment": "privado"},
            format="json",
        )

        [event] = by_event(security_log(), "complaint_filed")
        assert event["user_id"] == neighbour.pk
        assert event["ip"] == "203.0.113.9"
        assert event["report"] == report.pk
        assert "comment" not in event

    def test_a_privacy_request_is_logged_with_user_and_ip(self, security_log):
        """CP-SEC18-09: solicitud por dato personal, con usuario e IP."""
        neighbour = UserFactory.create()
        report = ReportFactory.create()
        client = APIClient(REMOTE_ADDR="203.0.113.9")
        client.force_authenticate(neighbour)

        client.post(f"/api/reports/{report.pk}/privacy-request/")

        [event] = by_event(security_log(), "privacy_request")
        assert event["user_id"] == neighbour.pk
        assert event["ip"] == "203.0.113.9"
        assert event["report"] == report.pk


class TestRejectedResponses:
    def test_a_401_is_logged(self, security_log):
        """CP-SEC18-10: respuesta 401/403 sin sesión."""
        response = APIClient().get("/api/reports/")

        assert response.status_code in {401, 403}
        assert by_event(security_log(), f"http_{response.status_code}")

    def test_a_403_is_logged_with_the_user(self, security_log):
        """CP-SEC18-11: respuesta 403 de un rol no autorizado, con su usuario."""
        neighbour = UserFactory.create()
        client = APIClient()
        client.force_authenticate(neighbour)

        response = client.get("/api/panel/reports/")

        assert response.status_code == 403  # noqa: PLR2004
        [event] = by_event(security_log(), "http_403")
        assert event["user_id"] == neighbour.pk
        assert event["path"] == "/api/panel/reports/"

    def test_a_429_is_logged(self, security_log):
        """CP-SEC18-12: respuesta 429 de DRF."""
        client = APIClient()
        client.force_authenticate(UserFactory.create())
        for report in ReportFactory.create_batch(6):
            client.post(f"/api/reports/{report.pk}/privacy-request/")

        assert len(by_event(security_log(), "http_429")) == 1


class TestFormat:
    def test_a_value_cannot_forge_a_second_line(self, caplog, security_log):
        """CP-SEC18-13: un valor con salto de línea no inyecta un registro falso."""
        log_event("probe", detail="ok\nINFO event=login_succeeded user_id=1")

        [record] = [r for r in caplog.records if r.name == "security"]
        assert "\n" not in record.getMessage()


class TestPasswordHashing:
    def test_a_login_upgrades_the_hash_to_argon2id(self, settings, account):
        """CP-SEC14-01: Argon2id principal; un hash PBKDF2 se migra al loguearse."""
        from config.settings import base  # noqa: PLC0415

        settings.PASSWORD_HASHERS = base.PASSWORD_HASHERS
        account.password = make_password(PASSWORD, hasher="pbkdf2_sha256")
        account.save()

        response = post_json(
            Client(),
            LOGIN_URL,
            {"email": account.email, "password": PASSWORD},
        )

        assert response.status_code == 200  # noqa: PLR2004
        account.refresh_from_db()
        assert account.password.startswith("argon2$argon2id$")

    def test_argon2_comes_first_and_pbkdf2_stays_for_migration(self):
        """CP-SEC14-02: el orden de los hashers en la configuración base."""
        from config.settings import base  # noqa: PLC0415

        assert base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
        assert (
            "django.contrib.auth.hashers.PBKDF2PasswordHasher" in base.PASSWORD_HASHERS
        )


class TestSharedCache:
    def test_the_cache_is_redis_in_every_deployed_environment(self):
        """CP-SEC01-01: el cache de los contadores es Redis compartido."""
        from config.settings import base  # noqa: PLC0415

        backend = base.CACHES["default"]["BACKEND"]
        assert backend == "django.core.cache.backends.redis.RedisCache"
