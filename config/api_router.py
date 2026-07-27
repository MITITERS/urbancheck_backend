from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from urbancheck.notifications.api.views import NotificationViewSet
from urbancheck.reports.api.views import CommentViewSet
from urbancheck.reports.api.views import ReportViewSet
from urbancheck.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("reports", ReportViewSet, basename="report")
router.register("comments", CommentViewSet, basename="comment")
router.register("notifications", NotificationViewSet, basename="notification")


app_name = "api"
urlpatterns = router.urls
