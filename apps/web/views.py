from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from apps.teams.helpers import get_open_invitations_for_user
from apps.teams.models import Team
from apps.users.models import CustomUser


def csrf_test(request):
    """
    Simple endpoint to test CSRF functionality in development.
    """
    if request.method == "GET":
        # Return current CSRF token and settings for debugging
        csrf_token = get_token(request)
        return JsonResponse(
            {
                "csrf_token": csrf_token,
                "csrf_cookie": request.META.get("CSRF_COOKIE", ""),
                "csrf_trusted_origins": getattr(settings, "CSRF_TRUSTED_ORIGINS", []),
                "csrf_cookie_samesite": getattr(settings, "CSRF_COOKIE_SAMESITE", ""),
                "csrf_cookie_secure": getattr(settings, "CSRF_COOKIE_SECURE", False),
                "csrf_cookie_httponly": getattr(settings, "CSRF_COOKIE_HTTPONLY", False),
                "cors_allowed_origins": getattr(settings, "CORS_ALLOWED_ORIGINS", []),
                "debug": settings.DEBUG,
                "method": request.method,
                "headers": dict(request.headers),
            }
        )

    elif request.method == "POST":
        # Test CSRF protection - this should work if CSRF is properly configured
        return JsonResponse(
            {
                "success": True,
                "message": "CSRF verification passed!",
                "received_data": request.POST.dict() if request.POST else {},
                "method": request.method,
            }
        )


@csrf_exempt
def csrf_exempt_test(request):
    """
    Test endpoint that bypasses CSRF protection.
    Use this to verify that CSRF is working by comparing with csrf_test.
    """
    if request.method == "POST":
        return JsonResponse(
            {
                "success": True,
                "message": "CSRF bypassed (this endpoint is exempt)",
                "received_data": request.POST.dict() if request.POST else {},
                "method": request.method,
            }
        )

    return JsonResponse(
        {
            "message": "This endpoint bypasses CSRF protection",
            "method": request.method,
        }
    )


def csrf_debug(request):
    """
    Debug endpoint to show all CSRF-related information.
    """
    context = {
        "csrf_token": get_token(request),
        "csrf_cookie": request.META.get("CSRF_COOKIE", ""),
        "csrf_trusted_origins": getattr(settings, "CSRF_TRUSTED_ORIGINS", []),
        "csrf_cookie_samesite": getattr(settings, "CSRF_COOKIE_SAMESITE", ""),
        "csrf_cookie_secure": getattr(settings, "CSRF_COOKIE_SECURE", False),
        "csrf_cookie_httponly": getattr(settings, "CSRF_COOKIE_HTTPONLY", False),
        "cors_allowed_origins": getattr(settings, "CORS_ALLOWED_ORIGINS", []),
        "debug": settings.DEBUG,
        "method": request.method,
        "headers": dict(request.headers),
        "cookies": request.COOKIES,
        "meta": {k: v for k, v in request.META.items() if "CSRF" in k or "ORIGIN" in k or "REFERER" in k},
    }
    return render(request, "web/csrf_debug.html", context)


def home(request):
    """Home page view."""
    if request.user.is_authenticated:
        team = request.team
        open_invitations = get_open_invitations_for_user(request.user)
        return render(
            request,
            "web/app_home.html",
            context={
                "team": team,
                "active_tab": "dashboard",
                "page_title": _("{team} Dashboard").format(team=team),
                "open_invitations": open_invitations,
            },
        )
    return render(request, "web/home.html")


def team_home(request, team_slug):
    """Team home page view."""
    team = Team.objects.get(slug=team_slug)
    return render(request, "web/team_home.html", {"team": team})


def simulate_error(request):
    """Simulate an error for testing error pages."""
    raise Exception("This is a simulated error for testing purposes.")


@method_decorator(csrf_exempt, name="dispatch")
class HealthCheck(View):
    """Health check endpoint for monitoring."""

    def get(self, request):
        """GET request for health check."""
        return JsonResponse(
            {
                "status": "healthy",
                "timestamp": timezone.now().isoformat(),
                "debug": settings.DEBUG,
            }
        )

    def post(self, request):
        """POST request for health check with additional checks."""
        try:
            # Check database connection
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            # Check if we can query basic models
            user_count = CustomUser.objects.count()
            team_count = Team.objects.count()

            return JsonResponse(
                {
                    "status": "healthy",
                    "timestamp": timezone.now().isoformat(),
                    "database": "connected",
                    "user_count": user_count,
                    "team_count": team_count,
                    "debug": settings.DEBUG,
                }
            )
        except Exception as e:
            return JsonResponse(
                {
                    "status": "unhealthy",
                    "timestamp": timezone.now().isoformat(),
                    "error": str(e),
                    "debug": settings.DEBUG,
                },
                status=500,
            )
