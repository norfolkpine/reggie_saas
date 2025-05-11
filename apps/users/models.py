import hashlib
import uuid
from functools import cached_property

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as AuthUserManager
from django.core import mail, validators
from django.db import models
from django.utils.translation import gettext_lazy as _
from timezone_field import TimeZoneField

from apps.users.helpers import validate_profile_picture


class DuplicateEmailError(Exception):
    """Raised when an email is already associated with a pre-existing user."""

    def __init__(self, message=None, email=None):
        """Set message and email to describe the exception."""
        self.message = message
        self.email = email
        super().__init__(self.message)


class UserManager(AuthUserManager):
    """Custom manager for User model with additional methods."""

    def get_user_by_sub_or_email(self, sub, email):
        """Fetch existing user by sub or email."""
        try:
            return self.get(sub=sub)
        except self.model.DoesNotExist as err:
            if not email:
                return None

            if settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION:
                try:
                    return self.get(email=email)
                except self.model.DoesNotExist:
                    pass
            elif (
                self.filter(email=email).exists()
                and not settings.OIDC_ALLOW_DUPLICATE_EMAILS
            ):
                raise DuplicateEmailError(
                    _(
                        "We couldn't find a user with this sub but the email is already "
                        "associated with a registered user."
                    )
                ) from err
        return None


def _get_avatar_filename(instance, filename):
    """Use random filename prevent overwriting existing files & to fix caching issues."""
    return f"profile-pictures/{uuid.uuid4()}.{filename.split('.')[-1]}"


class CustomUser(AbstractUser):
    """
    Custom user model that combines functionality from both docs and users apps.
    """

    objects = UserManager()

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    avatar = models.FileField(upload_to=_get_avatar_filename, blank=True, validators=[validate_profile_picture])

    # Fields from User model
    sub = models.CharField(
        _("sub"),
        help_text=_("Required. 255 characters or fewer. Letters, numbers, and @/./+/-/_/: characters only."),
        max_length=255,
        unique=True,
        validators=[
            validators.RegexValidator(
                regex=r"^[\w.@+-:]+\Z",
                message=_(
                    "Enter a valid sub. This value may contain only letters, numbers, and @/./+/-/_/: characters."
                ),
            )
        ],
        blank=True,
        null=True,
    )

    full_name = models.CharField(_("full name"), max_length=100, null=True, blank=True)
    short_name = models.CharField(_("short name"), max_length=20, null=True, blank=True)

    email = models.EmailField(_("identity email address"), blank=True, null=True)

    # Unlike the "email" field which stores the email coming from the OIDC token, this field
    # stores the email used by staff users to login to the admin site
    admin_email = models.EmailField(_("admin email address"), unique=True, blank=True, null=True)

    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default=None,
        verbose_name=_("language"),
        help_text=_("The language in which the user wants to see the interface."),
        null=True,
        blank=True,
    )
    timezone = TimeZoneField(
        choices_display="WITH_GMT_OFFSET",
        use_pytz=False,
        default=settings.TIME_ZONE,
        help_text=_("The timezone in which the user wants to see times."),
    )
    is_device = models.BooleanField(
        _("device"),
        default=False,
        help_text=_("Whether the user is a device or a real user."),
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "impress_user"
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self):
        return self.email or self.admin_email or str(self.id)

    def get_display_name(self) -> str:
        if self.get_full_name().strip():
            return self.get_full_name()
        return self.email or self.username

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            return self.avatar.url
        else:
            return "https://www.gravatar.com/avatar/{}?s=128&d=identicon".format(self.gravatar_id)

    @property
    def gravatar_id(self) -> str:
        # https://en.gravatar.com/site/implement/hash/
        return hashlib.md5(self.email.lower().strip().encode("utf-8")).hexdigest()

    @cached_property
    def has_verified_email(self):
        return EmailAddress.objects.filter(user=self, verified=True).exists()

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Email this user."""
        if not self.email:
            raise ValueError("User has no email address.")
        mail.send_mail(subject, message, from_email, [self.email], **kwargs)

    @cached_property
    def teams(self):
        """
        Get list of teams in which the user is, as a list of strings.
        Must be cached if retrieved remotely.
        """
        return []

    def save(self, *args, **kwargs):
        """
        If it's a new user, give its user access to the documents to which s.he was invited.
        Skip this for superusers.
        """
        is_adding = self._state.adding
        super().save(*args, **kwargs)

        if is_adding and not self.is_superuser:
            self._convert_valid_invitations()

    def _convert_valid_invitations(self):
        """
        Convert valid invitations to document accesses.
        Expired invitations are ignored.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.docs.models import Document, DocumentAccess, Invitation

        valid_invitations = Invitation.objects.filter(
            email=self.email,
            created_at__gte=(timezone.now() - timedelta(seconds=settings.INVITATION_VALIDITY_DURATION)),
        ).select_related("document")

        if not valid_invitations.exists():
            return

        DocumentAccess.objects.bulk_create(
            [
                DocumentAccess(user=self, document=invitation.document, role=invitation.role)
                for invitation in valid_invitations
            ]
        )

        # Set creator of documents if not yet set (e.g. documents created via server-to-server API)
        document_ids = [invitation.document_id for invitation in valid_invitations]
        Document.objects.filter(id__in=document_ids, creator__isnull=True).update(creator=self)

        valid_invitations.delete()
