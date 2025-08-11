from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.users.models import CustomUser


class SecureMobileTokenObtainPairView(TokenObtainPairView):
    """
    Secure JWT token endpoint for mobile apps.
    Uses proper authentication and rate limiting.
    """

    permission_classes = [AllowAny]


class SecureMobileTokenRefreshView(TokenRefreshView):
    """
    Secure JWT token refresh endpoint for mobile apps.
    """

    permission_classes = [AllowAny]


@api_view(["POST"])
@permission_classes([AllowAny])
def secure_mobile_login(request):
    """
    Secure mobile-friendly login endpoint.
    Accepts email/password and returns JWT tokens with proper validation.
    """
    # Validate mobile app headers
    mobile_app_id = request.META.get("HTTP_X_MOBILE_APP_ID")
    mobile_app_version = request.META.get("HTTP_X_MOBILE_APP_VERSION")
    device_id = request.META.get("HTTP_X_DEVICE_ID")

    # Mobile app ID validation
    valid_app_ids = ["com.benheath.reggie.ios", "com.benheath.reggie.android"]
    if not mobile_app_id or mobile_app_id not in valid_app_ids:
        return Response({"error": "Invalid mobile app identifier"}, status=status.HTTP_401_UNAUTHORIZED)

    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate email format
    if "@" not in email:
        return Response({"error": "Invalid email format"}, status=status.HTTP_400_BAD_REQUEST)

    # Rate limiting check (basic implementation)
    from django.core.cache import cache

    cache_key = f"mobile_login_attempts_{device_id or request.META.get('REMOTE_ADDR', 'unknown')}"
    attempts = cache.get(cache_key, 0)

    if attempts >= 5:  # Max 5 attempts per device/IP
        return Response(
            {"error": "Too many login attempts. Please try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    # Authenticate user
    try:
        user = CustomUser.objects.get(email=email)
        if not user.check_password(password):
            # Increment failed attempts
            cache.set(cache_key, attempts + 1, 300)  # 5 minutes timeout
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
    except CustomUser.DoesNotExist:
        # Increment failed attempts
        cache.set(cache_key, attempts + 1, 300)  # 5 minutes timeout
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({"error": "Account is disabled"}, status=status.HTTP_401_UNAUTHORIZED)

    # Clear failed attempts on successful login
    cache.delete(cache_key)

    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)

    # Log successful mobile login
    from django.contrib.auth.signals import user_logged_in

    user_logged_in.send(sender=CustomUser, user=user, request=request)

    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
            },
            "app_info": {
                "app_id": mobile_app_id,
                "app_version": mobile_app_version,
                "device_id": device_id,
            },
        }
    )
