from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.contrib.auth import get_user_model
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

CustomUser = get_user_model()


class CustomOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Custom OIDC authentication backend that works with CustomUser model and 2FA."""

    def create_user(self, claims):
        """Create a new user from OIDC claims."""
        email = claims.get("email")
        if not email:
            return None

        # Check if user already exists
        try:
            user = CustomUser.objects.get(email=email)
            return user
        except CustomUser.DoesNotExist:
            # Create new user
            user = CustomUser.objects.create_user(
                email=email,
                username=claims.get("preferred_username", email),
                first_name=claims.get("given_name", ""),
                last_name=claims.get("family_name", ""),
                is_active=True,
            )
            return user

    def update_user(self, user, claims):
        """Update user fields based on OIDC claims."""
        user.email = claims.get("email", user.email)
        user.first_name = claims.get("given_name", user.first_name)
        user.last_name = claims.get("family_name", user.last_name)
        user.save()
        return user

    def verify_claims(self, claims):
        """Verify required claims are present."""
        required_claims = ["email", "sub"]
        return all(claim in claims for claim in required_claims)

    def authenticate(self, request, **kwargs):
        """Authenticate user and handle 2FA if enabled."""
        user = super().authenticate(request, **kwargs)

        if user and is_mfa_enabled(user, [Authenticator.Type.TOTP]):
            # Store user ID in session for 2FA verification
            request.session["pending_oidc_user_id"] = user.id
            return None

        return user
