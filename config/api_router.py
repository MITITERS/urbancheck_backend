from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from urbancheck.municipalities.api.area_views import OperationalAreaViewSet
from urbancheck.municipalities.api.views import MunicipalityViewSet
from urbancheck.notifications.api.views import NotificationViewSet
from urbancheck.reports.api.moderation_views import ModerationAppealViewSet
from urbancheck.reports.api.moderation_views import ModerationViewSet
from urbancheck.reports.api.moderation_views import PlatformReportModerationViewSet
from urbancheck.reports.api.operator_views import OperatorReportViewSet
from urbancheck.reports.api.panel_views import PanelReportViewSet
from urbancheck.reports.api.privacy_views import PrivacyRequestViewSet
from urbancheck.reports.api.public_views import PublicReportView
from urbancheck.reports.api.statistics_views import PanelStatisticsView
from urbancheck.reports.api.validation_views import ValidationReportViewSet
from urbancheck.reports.api.views import CommentViewSet
from urbancheck.reports.api.views import ReportViewSet
from urbancheck.users.api.views import MunicipalAgentViewSet
from urbancheck.users.api.views import OperatorViewSet
from urbancheck.users.api.views import UserViewSet
from urbancheck.users.api.views import ValidatorViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("municipalities", MunicipalityViewSet, basename="municipality")
router.register("municipal-agents", MunicipalAgentViewSet, basename="municipal-agent")
router.register("validators", ValidatorViewSet, basename="validator")
router.register("operators", OperatorViewSet, basename="operator")
# Áreas operativas del municipio (US-039): gestión desde el panel y desplegable
# de asignación de US-028.
router.register(
    "operational-areas",
    OperationalAreaViewSet,
    basename="operational-area",
)
router.register("reports", ReportViewSet, basename="report")
# Panel municipal: superficie propia, siempre acotada por jurisdicción (US-034).
router.register("panel/reports", PanelReportViewSet, basename="panel-report")
# Validación en terreno: acotada por jurisdicción y por capacidad de validar.
router.register(
    "validation/reports",
    ValidationReportViewSet,
    basename="validation-report",
)
# Bandeja del operario: acotada a su área operativa y al trabajo vigente.
router.register(
    "operator/reports",
    OperatorReportViewSet,
    basename="operator-report",
)
# Solicitudes por dato personal visible (US-043): las resuelve el administrador
# de la plataforma, de todas las municipalidades, fuera de la capa de
# jurisdicción.
router.register(
    "platform/privacy-requests",
    PrivacyRequestViewSet,
    basename="privacy-request",
)
# Moderación de contenido (US-049): la bandeja del agente, acotada por
# jurisdicción, y la revisión del administrador, que no lo está.
router.register("panel/moderation", ModerationViewSet, basename="panel-moderation")
router.register(
    "panel/moderation-appeals",
    ModerationAppealViewSet,
    basename="moderation-appeal",
)
router.register(
    "platform/reports",
    PlatformReportModerationViewSet,
    basename="platform-report",
)
router.register("comments", CommentViewSet, basename="comment")
router.register("notifications", NotificationViewSet, basename="notification")


app_name = "api"
urlpatterns = [
    # Estadísticas del agente (US-023 y US-050): una sola respuesta para toda la
    # sección. No es un recurso con id, así que va fuera del router.
    path("panel/statistics/", PanelStatisticsView.as_view(), name="panel-statistics"),
    # La página pública de un reporte compartido (US-030): sin sesión.
    path(
        "public/reports/<uuid:token>/",
        PublicReportView.as_view(),
        name="public-report",
    ),
    *router.urls,
]
