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


def user_has_valid_totp_device(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.authenticator_set.filter(type=Authenticator.Type.TOTP).exists()
