"""Ben Heath SaaS URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/stable/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.i18n import JavaScriptCatalog
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.api.v2.views import PagesAPIViewSet
from wagtail.contrib.sitemaps import Sitemap
from wagtail.documents import urls as wagtaildocs_urls

from apps.subscriptions.urls import team_urlpatterns as subscriptions_team_urls
from apps.teams.urls import team_urlpatterns as single_team_urls
from apps.web.sitemaps import StaticViewSitemap
from apps.web.urls import team_urlpatterns as web_team_urls

from .admin import custom_admin_site

PagesAPIViewSet.schema = None  # hacky workaround for https://github.com/wagtail/wagtail/issues/8583

sitemaps = {
    "static": StaticViewSitemap(),
    "wagtail": Sitemap(),
}

# urls that are unique to using a team should go here
team_urlpatterns = [
    path("", include(web_team_urls)),
    path("subscription/", include(subscriptions_team_urls)),
    path("team/", include(single_team_urls)),
    path("example/", include("apps.teams_example.urls")),
]

# API v1 URL patterns
api_v1_patterns = [
    # path("auth/", include("apps.authentication.urls")),
    path("", include("apps.docs.urls")),
    path("chat/", include("apps.chat.urls")),
    path("group-chat/", include("apps.group_chat.urls")),
    path("reggie/", include("apps.reggie.urls")),
    path("slack/", include("apps.slack_integration.urls")),
    path("integrations/", include("apps.app_integrations.urls")),
    path("ai-images/", include("apps.ai_images.urls")),
    path("", include("apps.api.urls")),  # Base API endpoints
]

urlpatterns = [
    # Admin URLs
    path("admin/doc/", include("django.contrib.admindocs.urls")),
    path("admin/login/", RedirectView.as_view(pattern_name="account_login")),
    path("admin/", custom_admin_site.urls),
    # Core application URLs
    path("dashboard/", include("apps.dashboard.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("a/<slug:team_slug>/", include(team_urlpatterns)),
    # User management URLs
    path("accounts/", include("allauth.urls")),
    path("users/", include("apps.users.urls")),
    path("subscriptions/", include("apps.subscriptions.urls")),
    path("teams/", include("apps.teams.urls")),
    path("", include("apps.web.urls")),
    path("support/", include("apps.support.urls")),
    path("celery-progress/", include("celery_progress.urls")),
    # API routes
    path("api/v1/", include(api_v1_patterns)),
    # API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Third-party integrations
    path("stripe/", include("djstripe.urls", namespace="djstripe")),
    path("hijack/", include("hijack.urls", namespace="hijack")),
    # Wagtail CMS
    path("cms/login/", RedirectView.as_view(pattern_name="account_login")),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("content/", include(wagtail_urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.ENABLE_DEBUG_TOOLBAR:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
