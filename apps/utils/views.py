"""Utility views for the application."""

from django.http import JsonResponse


def csrf_failure(request, reason=""):
    """Custom CSRF failure view that returns JSON for API requests."""
    # Check if the request wants JSON (common for API/frontend requests)
    content_type = request.META.get("CONTENT_TYPE", "")
    accept_header = request.META.get("HTTP_ACCEPT", "")
    
    if "application/json" in content_type or "application/json" in accept_header:
        return JsonResponse(
            {"error": "CSRF verification failed", "detail": str(reason)},
            status=403
        )
    
    # For regular HTML requests, return default HTML error
    from django.views.csrf import csrf_failure as django_csrf_failure
    return django_csrf_failure(request, reason=reason)
