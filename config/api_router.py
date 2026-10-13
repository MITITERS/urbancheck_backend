from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from urbancheck.municipalities.api.area_views import OperationalAreaViewSet
from urbancheck.municipalities.api.views import MunicipalityViewSet
from urbancheck.notifications.api.views import NotificationViewSet
from urbancheck.reports.api.operator_views import OperatorReportViewSet
from urbancheck.reports.api.panel_views import PanelReportViewSet
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
router.register("comments", CommentViewSet, basename="comment")
router.register("notifications", NotificationViewSet, basename="notification")


app_name = "api"
urlpatterns = router.urls
