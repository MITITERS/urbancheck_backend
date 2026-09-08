from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from config.deeplink import android_assetlinks
from config.deeplink import apple_app_site_association
from config.deeplink import reset_password_web_fallback
from urbancheck.municipalities.api.geo_views import LocalityListView
from urbancheck.municipalities.api.geo_views import ProvinceListView
from urbancheck.notifications.api.preferences import NotificationPreferenceView

urlpatterns = [
    path("", TemplateView.as_view(template_name="pages/home.html"), name="home"),
    path(
        "about/",
        TemplateView.as_view(template_name="pages/about.html"),
        name="about",
    ),
    # Universal Links (iOS) / App Links (Android) + fallback web del reset
    path(
        ".well-known/apple-app-site-association",
        apple_app_site_association,
    ),
    path(".well-known/assetlinks.json", android_assetlinks),
    path("reset-password", reset_password_web_fallback, name="reset_password"),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("urbancheck.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
    # Your stuff: custom urls includes go here
    # ...
    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]

# API URLS
urlpatterns += [
    # API base url
    path("api/", include("config.api_router")),
    # DRF auth token
    path("api/auth-token/", obtain_auth_token, name="obtain_auth_token"),
    path(
        "api/notification-preferences/",
        NotificationPreferenceView.as_view(),
        name="notification-preferences",
    ),
    path("api/geo/provinces/", ProvinceListView.as_view(), name="geo-provinces"),
    path(
        "api/geo/provinces/<str:province_id>/localities/",
        LocalityListView.as_view(),
        name="geo-localities",
    ),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
            *urlpatterns,
        ]
