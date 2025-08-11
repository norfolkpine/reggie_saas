import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


class MobileAppAuthentication(BaseAuthentication):
    """
    Custom authentication for mobile apps that validates requests securely.
    """

    def authenticate(self, request):
        # Check for mobile app identifier header
        mobile_app_header = request.META.get("HTTP_X_MOBILE_APP_ID")
        if not mobile_app_header:
            return None

        # Validate mobile app identifier (you can customize this)
        valid_app_ids = getattr(settings, "MOBILE_APP_IDS", [])
        if mobile_app_header not in valid_app_ids:
            return None

        # For login endpoints, allow without authentication
        if request.path.endswith("/login/") or request.path.endswith("/token/"):
            return None

        # For other endpoints, require JWT token
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Bearer token required")

        token = auth_header.split(" ")[1]

        try:
            # Decode JWT token
            payload = jwt.decode(
                token, settings.SIMPLE_JWT["SIGNING_KEY"], algorithms=[settings.SIMPLE_JWT["ALGORITHM"]]
            )

            user_id = payload.get("user_id")
            if not user_id:
                raise AuthenticationFailed("Invalid token")

            user = User.objects.get(id=user_id, is_active=True)
            return (user, token)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token")
        except User.DoesNotExist:
            raise AuthenticationFailed("User not found")


class SecureMobileAuthentication(BaseAuthentication):
    """
    Secure authentication for mobile apps with additional security measures.
    """

    def authenticate(self, request):
        # Check for required security headers
        required_headers = ["HTTP_X_MOBILE_APP_ID", "HTTP_X_MOBILE_APP_VERSION", "HTTP_X_DEVICE_ID"]

        for header in required_headers:
            if not request.META.get(header):
                return None

        # Validate app ID and version
        app_id = request.META.get("HTTP_X_MOBILE_APP_ID")
        app_version = request.META.get("HTTP_X_MOBILE_APP_VERSION")
        device_id = request.META.get("HTTP_X_DEVICE_ID")

        # You can add validation logic here
        valid_app_ids = getattr(settings, "MOBILE_APP_IDS", [])
        if app_id not in valid_app_ids:
            return None

        # For login endpoints, allow without authentication
        if request.path.endswith("/login/") or request.path.endswith("/token/"):
            return None

        # For other endpoints, require JWT token
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Bearer token required")

        token = auth_header.split(" ")[1]

        try:
            # Decode JWT token
            payload = jwt.decode(
                token, settings.SIMPLE_JWT["SIGNING_KEY"], algorithms=[settings.SIMPLE_JWT["ALGORITHM"]]
            )

            user_id = payload.get("user_id")
            if not user_id:
                raise AuthenticationFailed("Invalid token")

            user = User.objects.get(id=user_id, is_active=True)
            return (user, token)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token")
        except User.DoesNotExist:
            raise AuthenticationFailed("User not found")
