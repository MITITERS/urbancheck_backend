"""Limitación de intentos y de tasa (Sprint 5, punto 5.1 — deuda del Sprint 4).

Los límites de allauth (login, recuperación, confirmación, registro) y los de
DRF (reportes, comentarios, denuncias, solicitudes por dato personal) se
prueban con sus valores por defecto, salvo donde se dice lo contrario: el
número exacto es parte de lo que se promete en el documento de Seguridad.
"""

from __future__ import annotations

import json

import pytest
from allauth.account.models import EmailAddress
from django.test import Client
from rest_framework.test import APIClient

from urbancheck.common.security import client_ip
from urbancheck.common.throttling import ScopedThrottle
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportComplaint
from urbancheck.reports.tests.factories import ReportFactory
from urbancheck.reports.tests.test_duplicate_reports import create_report
from urbancheck.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

LOGIN_URL = "/_allauth/app/v1/auth/login"
SIGNUP_URL = "/_allauth/app/v1/auth/signup"
PASSWORD_REQUEST_URL = "/_allauth/app/v1/auth/password/request"  # noqa: S105
EMAIL_URL = "/_allauth/app/v1/account/email"

PASSWORD = "Xk7#mP9@qLz2!"  # noqa: S105
HTTP_TOO_MANY = 429


def post_json(client: Client, url: str, data: dict, **headers):
    return client.post(
        url,
        json.dumps(data),
        content_type="application/json",
        **headers,
    )


def api_client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def account():
    user = UserFactory.create(email="vecina@example.com")
    user.set_password(PASSWORD)
    user.save()
    return user


class TestFailedLogins:
    def test_the_sixth_failed_attempt_on_an_account_answers_429(self, account):
        """CP-SEC02-01: 5 intentos fallidos por cuenta; el 6.º responde 429."""
        client = Client()
        for _ in range(5):
            response = post_json(
                client,
                LOGIN_URL,
                {"email": account.email, "password": "incorrecta"},
            )
            assert response.status_code == 400  # noqa: PLR2004

        response = post_json(
            client,
            LOGIN_URL,
            {"email": account.email, "password": "incorrecta"},
        )

        assert response.status_code == HTTP_TOO_MANY
        codes = {error["code"] for error in response.json()["errors"]}
        assert codes == {"too_many_login_attempts"}

    def test_the_right_password_is_also_held_back_while_locked(self, account):
        """CP-SEC02-02: con la cuenta frenada, ni la contraseña correcta entra."""
        client = Client()
        for _ in range(5):
            post_json(client, LOGIN_URL, {"email": account.email, "password": "x"})

        response = post_json(
            client,
            LOGIN_URL,
            {"email": account.email, "password": PASSWORD},
        )

        assert response.status_code == HTTP_TOO_MANY
        assert "session_token" not in response.content.decode()

    def test_the_lock_is_per_account(self, account):
        """CP-SEC02-03: frenar una cuenta no frena a otra desde la misma IP."""
        other = UserFactory.create(email="otra@example.com")
        other.set_password(PASSWORD)
        other.save()
        client = Client()
        for _ in range(5):
            post_json(client, LOGIN_URL, {"email": account.email, "password": "x"})

        response = post_json(
            client,
            LOGIN_URL,
            {"email": other.email, "password": PASSWORD},
        )

        assert response.status_code == 200  # noqa: PLR2004

    def test_the_wrong_credentials_message_stays_generic(self, account):
        """CP-SEC02-04: el error no dice si la cuenta existe."""
        client = Client()
        known = post_json(client, LOGIN_URL, {"email": account.email, "password": "x"})
        unknown = post_json(
            client,
            LOGIN_URL,
            {"email": "nadie@example.com", "password": "x"},
        )

        assert known.status_code == unknown.status_code == 400  # noqa: PLR2004
        assert known.json()["errors"] == unknown.json()["errors"]


class TestPasswordReset:
    def test_the_fourth_request_in_an_hour_answers_429(self, account):
        """CP-SEC02-05: 3 pedidos de recuperación por cuenta por hora."""
        client = Client()
        for _ in range(3):
            response = post_json(client, PASSWORD_REQUEST_URL, {"email": account.email})
            assert response.status_code == 200  # noqa: PLR2004

        response = post_json(client, PASSWORD_REQUEST_URL, {"email": account.email})

        assert response.status_code == HTTP_TOO_MANY


class TestEmailConfirmation:
    def test_resending_the_confirmation_is_limited(self, account, settings):
        """CP-SEC02-06: el reenvío de la confirmación de correo tiene tope por cuenta.

        La espera de 3 minutos entre envíos haría que el segundo ya responda
        429; se la saca para probar el tope por hora de 3.
        """
        settings.ACCOUNT_RATE_LIMITS = {
            **settings.ACCOUNT_RATE_LIMITS,
            "confirm_email": "3/h/key",
        }
        EmailAddress.objects.create(
            user=account,
            email=account.email,
            primary=True,
            verified=False,
        )
        client = Client()
        login = post_json(
            client,
            LOGIN_URL,
            {"email": account.email, "password": PASSWORD},
        )
        token = login.json()["meta"]["session_token"]
        headers = {"HTTP_X_SESSION_TOKEN": token}

        statuses = [
            client.put(
                EMAIL_URL,
                json.dumps({"email": account.email}),
                content_type="application/json",
                **headers,
            ).status_code
            for _ in range(4)
        ]

        assert statuses[:3] == [200, 200, 200]
        assert statuses[3] == HTTP_TOO_MANY


class TestSignup:
    def test_signups_are_limited_per_ip(self, settings):
        """CP-SEC02-07: el registro de cuentas tiene tope por IP."""
        settings.ACCOUNT_RATE_LIMITS = {
            **settings.ACCOUNT_RATE_LIMITS,
            "signup": "2/h/ip",
        }
        client = Client()
        statuses = [
            post_json(
                client,
                SIGNUP_URL,
                {"email": f"nueva{n}@example.com", "password": PASSWORD, "name": "Ana"},
            ).status_code
            for n in range(3)
        ]

        assert statuses[2] == HTTP_TOO_MANY
        assert statuses[:2] != [HTTP_TOO_MANY, HTTP_TOO_MANY]


class TestTrustedProxies:
    """CP-SEC04-xx: detrás de Nginx, el límite por IP cuenta la IP del cliente."""

    @pytest.fixture
    def behind_one_proxy(self, settings):
        settings.NUM_PROXIES = 1
        settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
        settings.ACCOUNT_RATE_LIMITS = {
            **settings.ACCOUNT_RATE_LIMITS,
            "signup": "1/h/ip",
        }

    def signup(self, client, n, forwarded_for):
        return post_json(
            client,
            SIGNUP_URL,
            {"email": f"proxy{n}@example.com", "password": PASSWORD, "name": "Ana"},
            HTTP_X_FORWARDED_FOR=forwarded_for,
        )

    def test_two_clients_behind_the_proxy_do_not_share_a_counter(
        self,
        behind_one_proxy,
    ):
        """CP-SEC04-01: dos ``X-Forwarded-For`` distintos, dos contadores."""
        client = Client()
        first = self.signup(client, 1, "203.0.113.10")
        exhausted = self.signup(client, 2, "203.0.113.10")
        other_client = self.signup(client, 3, "198.51.100.20")

        assert first.status_code != HTTP_TOO_MANY
        assert exhausted.status_code == HTTP_TOO_MANY
        assert other_client.status_code != HTTP_TOO_MANY

    def test_the_proxy_counts_from_the_right(self, behind_one_proxy, rf):
        """CP-SEC04-02: lo que agrega el cliente a la izquierda no cuenta."""
        request = rf.get(
            "/",
            HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.10",
            REMOTE_ADDR="172.18.0.5",
        )

        assert client_ip(request) == "203.0.113.10"
        assert ScopedThrottle("reports").get_ident(request) == "203.0.113.10"

    def test_without_proxies_the_header_is_ignored(self, settings, rf):
        """CP-SEC04-03: sin proxies, ``X-Forwarded-For`` no elige la IP.

        Es el default. Si se confiara en la cabecera, cada pedido con un valor
        inventado empezaría un contador nuevo y no habría límite por IP.
        """
        settings.NUM_PROXIES = 0
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
        request = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR="203.0.113.7")

        assert client_ip(request) == "203.0.113.7"
        assert ScopedThrottle("reports").get_ident(request) == "203.0.113.7"


class TestComplaintThrottle:
    def test_the_eleventh_complaint_of_the_day_answers_429(self):
        """CP-SEC03-01: 10 denuncias por día por usuario; la 11.ª responde 429."""
        neighbour = UserFactory.create()
        client = api_client_for(neighbour)
        reports = ReportFactory.create_batch(11)
        for report in reports[:10]:
            response = client.post(
                f"/api/reports/{report.pk}/complaints/",
                {"reason": ReportComplaint.Reason.REPORTE_FALSO},
                format="json",
            )
            assert response.status_code == 201  # noqa: PLR2004

        response = client.post(
            f"/api/reports/{reports[10].pk}/complaints/",
            {"reason": ReportComplaint.Reason.REPORTE_FALSO},
            format="json",
        )

        assert response.status_code == HTTP_TOO_MANY
        assert response.data["code"] == "throttled"
        assert response["Retry-After"]
        assert not ReportComplaint.objects.filter(report=reports[10]).exists()

    def test_the_limit_is_per_user(self):
        """CP-SEC03-02: el cupo de un vecino no lo consume otro."""
        reports = ReportFactory.create_batch(11)
        heavy = api_client_for(UserFactory.create())
        for report in reports[:10]:
            heavy.post(
                f"/api/reports/{report.pk}/complaints/",
                {"reason": ReportComplaint.Reason.REPORTE_FALSO},
                format="json",
            )

        response = api_client_for(UserFactory.create()).post(
            f"/api/reports/{reports[10].pk}/complaints/",
            {"reason": ReportComplaint.Reason.REPORTE_FALSO},
            format="json",
        )

        assert response.status_code == 201  # noqa: PLR2004


class TestPrivacyRequestThrottle:
    def test_the_sixth_request_of_the_day_answers_429_and_hides_nothing(self):
        """CP-SEC03-03: 5 solicitudes por dato personal por día; la 6.ª no oculta."""
        client = api_client_for(UserFactory.create())
        reports = ReportFactory.create_batch(6)
        for report in reports[:5]:
            response = client.post(f"/api/reports/{report.pk}/privacy-request/")
            assert response.status_code == 201  # noqa: PLR2004

        response = client.post(f"/api/reports/{reports[5].pk}/privacy-request/")

        assert response.status_code == HTTP_TOO_MANY
        assert Report.objects.publicly_visible().filter(pk=reports[5].pk).exists()
        assert not ReportComplaint.objects.filter(report=reports[5]).exists()

    def test_the_complaint_endpoint_cannot_dodge_the_limit(self):
        """CP-SEC03-04: el motivo de dato personal por ``complaints/`` cuenta igual.

        Son dos caminos al mismo circuito de US-043; si cada uno llevara su
        cuenta, una cuenta ocultaría el doble de reportes.
        """
        client = api_client_for(UserFactory.create())
        reports = ReportFactory.create_batch(6)
        for report in reports[:5]:
            client.post(f"/api/reports/{report.pk}/privacy-request/")

        response = client.post(
            f"/api/reports/{reports[5].pk}/complaints/",
            {"reason": ReportComplaint.Reason.DATO_PERSONAL},
            format="json",
        )

        assert response.status_code == HTTP_TOO_MANY
        assert Report.objects.publicly_visible().filter(pk=reports[5].pk).exists()


class TestCommentThrottle:
    def test_the_sixty_first_comment_in_an_hour_answers_429(self):
        """CP-SEC03-05: 60 comentarios por hora por usuario."""
        report = ReportFactory.create()
        client = api_client_for(UserFactory.create())
        url = f"/api/reports/{report.pk}/comments/"
        for n in range(60):
            response = client.post(url, {"text": f"Comentario {n}"}, format="json")
            assert response.status_code == 201  # noqa: PLR2004

        response = client.post(url, {"text": "Uno más"}, format="json")

        assert response.status_code == HTTP_TOO_MANY

    def test_reading_comments_is_not_limited(self):
        """CP-SEC03-06: el límite es del alta, no de la lectura."""
        report = ReportFactory.create()
        client = api_client_for(UserFactory.create())
        url = f"/api/reports/{report.pk}/comments/"
        for _ in range(60):
            client.post(url, {"text": "Hola"}, format="json")

        assert client.get(url).status_code == 200  # noqa: PLR2004


class TestReportCreationThrottle:
    def test_the_twenty_first_report_in_an_hour_answers_429(self, settings):
        """CP-SEC03-07: 20 reportes por hora por usuario.

        Los puntos están separados 100 m para que ninguno sea duplicado del
        anterior (US-026) y el límite sea lo único que frena el 21.º.
        """
        client = api_client_for(UserFactory.create())
        for n in range(20):
            response = create_report(client, point=(-32.40 + n * 0.001, -63.24))
            assert response.status_code == 201, response.data  # noqa: PLR2004

        response = create_report(client, point=(-32.30, -63.24))

        assert response.status_code == HTTP_TOO_MANY
        assert Report.objects.count() == 20  # noqa: PLR2004

    def test_the_rate_is_read_from_configuration(self, settings):
        """CP-SEC03-08: la tasa se cambia por configuración, sin tocar código."""
        settings.REST_FRAMEWORK = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "reports": "1/hour",
            },
        }
        client = api_client_for(UserFactory.create())

        assert create_report(client, point=(-32.40, -63.24)).status_code == 201  # noqa: PLR2004
        assert (
            create_report(client, point=(-32.30, -63.24)).status_code == HTTP_TOO_MANY
        )
