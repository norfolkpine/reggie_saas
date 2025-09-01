import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from allauth.account.models import EmailAddress

User = get_user_model()


class DjangoAllauthSessionAuthentication(SessionAuthentication):
    """
    Custom session authentication that works with Django Allauth headless sessions.
    This extends DRF's SessionAuthentication to handle Django Allauth session format.
    """
    
    def authenticate(self, request):
        """
        Returns a `User` if the request session currently has a logged in user.
        Otherwise returns `None`.
        """
        # Get the session key from cookies
        session_cookie_name = getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid')
        session_key = request.COOKIES.get(session_cookie_name)
        
        if not session_key:
            return None
            
        try:
            # Get the session from database
            session = Session.objects.get(session_key=session_key)
            session_data = session.get_decoded()
            
            # Check if user is authenticated in this session
            user_id = session_data.get('_auth_user_id')
            if not user_id:
                return None
            
            # Get the user
            user = User.objects.get(pk=user_id, is_active=True)
            
            # Enforce CSRF check
            self.enforce_csrf(request)
            
            return (user, None)
            
        except (Session.DoesNotExist, User.DoesNotExist, ValueError, KeyError):
            return None
    
    def authenticate_header(self, request):
        return 'Session'


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
        request.META.get("HTTP_X_MOBILE_APP_VERSION")
        request.META.get("HTTP_X_DEVICE_ID")

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
