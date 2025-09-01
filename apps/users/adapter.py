from typing import Any

from allauth.account import app_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_email, user_field
from allauth.headless.adapter import DefaultHeadlessAdapter
from allauth.mfa.models import Authenticator
from django.utils import timezone


class EmailAsUsernameAdapter(DefaultAccountAdapter):
    """
    Adapter that always sets the username equal to the user's email address.
    """

    def populate_username(self, request, user):
        # override the username population to always use the email
        user_field(user, app_settings.USER_MODEL_USERNAME_FIELD, user_email(user))


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    """
    Adapter that can be used to disable public sign-ups for your app.
    """

    def is_open_for_signup(self, request):
        # see https://stackoverflow.com/a/29799664/8207
        return False


class CustomHeadlessAdapter(DefaultHeadlessAdapter):
    def authenticate(self, request, **credentials):
        """
        Custom authentication for headless API.
        """
        from django.contrib.auth import authenticate
        
        # Handle email-based authentication
        if 'email' in credentials and 'password' in credentials:
            email = credentials['email']
            password = credentials['password']
            
            # Try email authentication first
            user = authenticate(request, email=email, password=password)
            if user and user.is_active:
                return user
                
            # Try username authentication as fallback
            user = authenticate(request, username=email, password=password)
            if user and user.is_active:
                return user
        
        return super().authenticate(request, **credentials)
    
    def serialize_user(self, user) -> dict[str, Any]:
        data = super().serialize_user(user)

        # Basic user fields
        data["avatar_url"] = user.avatar_url
        data["first_name"] = user.first_name
        data["last_name"] = user.last_name
        data["full_name"] = user.full_name
        data["short_name"] = user.short_name
        data["language"] = user.language
        data["timezone"] = str(user.timezone) if user.timezone else None
        data["is_device"] = user.is_device

        # Computed properties
        data["display_name"] = user.get_display_name()
        data["has_verified_email"] = user.has_verified_email
        data["gravatar_id"] = user.gravatar_id
        data["is_superuser"] = user.is_superuser

        # User info and stats
        data["user_info"] = {
            "account_age_days": (timezone.now() - user.date_joined).days,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "is_device_user": user.is_device,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "is_active": user.is_active,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        }

        return data


class CustomAccountAdapter(EmailAsUsernameAdapter):
    """
    Custom account adapter that handles email-based authentication
    and integrates with team invitations.
    """
    
    def authenticate(self, request, **credentials):
        """
        Authenticate user with email and password.
        """
        from django.contrib.auth import authenticate
        
        # Try to authenticate with email as username
        if 'email' in credentials and 'password' in credentials:
            email = credentials['email']
            password = credentials['password']
            
            # First try direct email authentication
            user = authenticate(request, email=email, password=password)
            if user:
                return user
                
            # If that fails, try username authentication (for existing users)
            user = authenticate(request, username=email, password=password)
            if user:
                return user
        
        return None
    
    def get_login_redirect_url(self, request):
        """
        Handle post-login redirects, including team invitations.
        """
        from apps.teams.invitations import get_invite_from_session, process_invitation, clear_invite_from_session
        
        # Check for pending team invitation
        invitation_id = get_invite_from_session(request)
        if invitation_id:
            try:
                process_invitation(request, invitation_id)
                clear_invite_from_session(request)
            except Exception as e:
                # Log the error but don't break the login flow
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to process invitation {invitation_id}: {e}")
        
        return super().get_login_redirect_url(request)


def user_has_valid_totp_device(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.authenticator_set.filter(type=Authenticator.Type.TOTP).exists()
