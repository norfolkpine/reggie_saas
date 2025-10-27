"""
Declare and configure the models for the impress core application
"""

# pylint: disable=too-many-lines

import contextlib
import hashlib
import smtplib
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from logging import getLogger

from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db import models, transaction
from django.db.models.functions import Left, Length
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import get_language, override
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError
from treebeard.mp_tree import MP_Node, MP_NodeManager, MP_NodeQuerySet

# Removed: from google.cloud import storage
# Reason: Use get_storage_client() instead to ensure proper GCS credentials
# (bh-opie-storage service account with object permissions)
from apps.teams.models import Membership
from apps.users.models import CustomUser
from apps.opie.utils.gcs_utils import get_storage_client

logger = getLogger(__name__)


def get_trashbin_cutoff():
    """
    Calculate the cutoff datetime for soft-deleted items based on the retention policy.

    The function returns the current datetime minus the number of days specified in
    the TRASHBIN_CUTOFF_DAYS setting, indicating the oldest date for items that can
    remain in the trash bin.

    Returns:
        datetime: The cutoff datetime for soft-deleted items.
    """
    return timezone.now() - timedelta(days=settings.TRASHBIN_CUTOFF_DAYS)


class LinkRoleChoices(models.TextChoices):
    """Defines the possible roles a link can offer on a document."""

    READER = "reader", _("Reader")  # Can read
    EDITOR = "editor", _("Editor")  # Can read and edit


class RoleChoices(models.TextChoices):
    """Defines the possible roles a user can have in a resource."""

    READER = "reader", _("Reader")  # Can read
    EDITOR = "editor", _("Editor")  # Can read and edit
    ADMIN = "administrator", _("Administrator")  # Can read, edit, delete and share
    OWNER = "owner", _("Owner")


PRIVILEGED_ROLES = [RoleChoices.ADMIN, RoleChoices.OWNER]


class LinkReachChoices(models.TextChoices):
    """Defines types of access for links"""

    RESTRICTED = (
        "restricted",
        _("Restricted"),
    )  # Only users with a specific access can read/edit the document
    AUTHENTICATED = (
        "authenticated",
        _("Authenticated"),
    )  # Any authenticated user can access the document
    PUBLIC = "public", _("Public")  # Even anonymous users can access the document

    @classmethod
    def get_select_options(cls, ancestors_links):
        """
        Determines the valid select options for link reach and link role depending on the
        list of ancestors' link reach/role.

        Args:
            ancestors_links: List of dictionaries, each with 'link_reach' and 'link_role' keys
                             representing the reach and role of ancestors links.

        Returns:
            Dictionary mapping possible reach levels to their corresponding possible roles.
        """
        # If no ancestors, return all options
        if not ancestors_links:
            return dict.fromkeys(cls.values, LinkRoleChoices.values)

        # Initialize result with all possible reaches and role options as sets
        result = {reach: set(LinkRoleChoices.values) for reach in cls.values}

        # Group roles by reach level
        reach_roles = defaultdict(set)
        for link in ancestors_links:
            reach_roles[link["link_reach"]].add(link["link_role"])

        # Apply constraints based on ancestor links
        if LinkRoleChoices.EDITOR in reach_roles[cls.RESTRICTED]:
            result[cls.RESTRICTED].discard(LinkRoleChoices.READER)

        if LinkRoleChoices.EDITOR in reach_roles[cls.AUTHENTICATED]:
            result[cls.AUTHENTICATED].discard(LinkRoleChoices.READER)
            result.pop(cls.RESTRICTED, None)
        elif LinkRoleChoices.READER in reach_roles[cls.AUTHENTICATED]:
            result[cls.RESTRICTED].discard(LinkRoleChoices.READER)

        if LinkRoleChoices.EDITOR in reach_roles[cls.PUBLIC]:
            result[cls.PUBLIC].discard(LinkRoleChoices.READER)
            result.pop(cls.AUTHENTICATED, None)
            result.pop(cls.RESTRICTED, None)
        elif LinkRoleChoices.READER in reach_roles[cls.PUBLIC]:
            result[cls.AUTHENTICATED].discard(LinkRoleChoices.READER)
            result.get(cls.RESTRICTED, set()).discard(LinkRoleChoices.READER)

        # Convert roles sets to lists while maintaining the order from LinkRoleChoices
        for reach, roles in result.items():
            result[reach] = [role for role in LinkRoleChoices.values if role in roles]

        return result


class DuplicateEmailError(Exception):
    """Raised when an email is already associated with a pre-existing user."""

    def __init__(self, message=None, email=None):
        """Set message and email to describe the exception."""
        self.message = message
        self.email = email
        super().__init__(self.message)


class BaseModel(models.Model):
    """
    Serves as an abstract base model for other models, ensuring that records are validated
    before saving as Django doesn't do it by default.

    Includes fields common to all models: a UUID primary key and creation/update timestamps.
    """

    id = models.UUIDField(
        verbose_name=_("id"),
        help_text=_("primary key for the record as UUID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(
        verbose_name=_("created on"),
        help_text=_("date and time at which a record was created"),
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        verbose_name=_("updated on"),
        help_text=_("date and time at which a record was last updated"),
        auto_now=True,
        editable=False,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Call `full_clean` before saving."""
        self.full_clean()
        super().save(*args, **kwargs)


class BaseAccess(BaseModel):
    """Base model for accesses to handle resources."""

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    team = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.READER)

    class Meta:
        abstract = True

    def _get_roles(self, resource, user):
        """
        Get the roles a user has on a resource.
        """
        roles = []
        if user.is_authenticated:
            # team_ids = Membership.objects.filter(user=user).values_list("team_id", flat=True)
            team_ids = list(Membership.objects.filter(user=user).values_list("team_id", flat=True))

            try:
                roles = self.user_roles or []
            except AttributeError:
                try:
                    roles = (
                        resource.accesses.all()
                        .filter(
                            models.Q(user=user) | models.Q(team__in=team_ids),
                        )
                        .values_list("role", flat=True)
                    )
                except (self._meta.model.DoesNotExist, IndexError):
                    roles = []

        return roles

    def _get_abilities(self, resource, user):
        """
        Compute and return abilities for a given user taking into account
        the current state of the object.
        """
        roles = self._get_roles(resource, user)

        is_owner_or_admin = bool(set(roles).intersection({RoleChoices.OWNER, RoleChoices.ADMIN}))
        if self.role == RoleChoices.OWNER:
            can_delete = RoleChoices.OWNER in roles and resource.accesses.filter(role=RoleChoices.OWNER).count() > 1
            set_role_to = [RoleChoices.ADMIN, RoleChoices.EDITOR, RoleChoices.READER] if can_delete else []
        else:
            can_delete = is_owner_or_admin
            set_role_to = []
            if RoleChoices.OWNER in roles:
                set_role_to.append(RoleChoices.OWNER)
            if is_owner_or_admin:
                set_role_to.extend([RoleChoices.ADMIN, RoleChoices.EDITOR, RoleChoices.READER])

        # Remove the current role as we don't want to propose it as an option
        with contextlib.suppress(ValueError):
            set_role_to.remove(self.role)

        return {
            "destroy": can_delete,
            "update": bool(set_role_to),
            "partial_update": bool(set_role_to),
            "retrieve": bool(roles),
            "set_role_to": set_role_to,
        }


class DocumentQuerySet(MP_NodeQuerySet):
    """
    Custom queryset for the Document model, providing additional methods
    to filter documents based on user permissions.
    """

    def readable_per_se(self, user):
        """
        Filters the queryset to return documents on which the given user has
        direct access, team access or link access. This will not return all the
        documents that a user can read because it can be obtained via an ancestor.
        :param user: The user for whom readable documents are to be fetched.
        :return: A queryset of documents for which the user has direct access,
            team access or link access.
        """
        if user.is_authenticated:
            # team_ids = Membership.objects.filter(user=user).values_list("team_id", flat=True )
            team_ids = list(Membership.objects.filter(user=user).values_list("team_id", flat=True))
            return self.filter(
                models.Q(accesses__user=user)
                | models.Q(accesses__team__in=team_ids)
                | ~models.Q(link_reach=LinkReachChoices.RESTRICTED)
            )

        return self.filter(link_reach=LinkReachChoices.PUBLIC)


class DocumentManager(MP_NodeManager.from_queryset(DocumentQuerySet)):
    """
    Custom manager for the Document model, enabling the use of the custom
    queryset methods directly from the model manager.
    """

    def get_queryset(self):
        """Sets the custom queryset as the default."""
        return self._queryset_class(self.model).order_by("path")


class Document(MP_Node, BaseModel):
    """Pad document carrying the content."""

    title = models.CharField(_("title"), max_length=255, null=True, blank=True)
    excerpt = models.TextField(_("excerpt"), max_length=300, null=True, blank=True)
    link_reach = models.CharField(
        max_length=20,
        choices=LinkReachChoices.choices,
        default=LinkReachChoices.RESTRICTED,
    )
    link_role = models.CharField(max_length=20, choices=LinkRoleChoices.choices, default=LinkRoleChoices.READER)
    creator = models.ForeignKey(
        CustomUser,
        on_delete=models.RESTRICT,
        related_name="documents_created",
        blank=True,
        null=True,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    ancestors_deleted_at = models.DateTimeField(null=True, blank=True)
    duplicated_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="duplicates",
        editable=False,
        blank=True,
        null=True,
    )
    attachments = ArrayField(
        models.CharField(max_length=255),
        default=list,
        editable=False,
        blank=True,
        null=True,
    )

    _content = None

    # Tree structure
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    steplen = 7  # nb siblings max: 3,521,614,606,208
    node_order_by = []  # Manual ordering

    path = models.CharField(max_length=7 * 36, unique=True, db_collation="C")

    objects = DocumentManager()

    class Meta:
        db_table = "impress_document"
        ordering = ("path",)
        verbose_name = _("Document")
        verbose_name_plural = _("Documents")
        constraints = [
            models.CheckConstraint(
                check=(models.Q(deleted_at__isnull=True) | models.Q(deleted_at=models.F("ancestors_deleted_at"))),
                name="check_deleted_at_matches_ancestors_deleted_at_when_set",
            ),
        ]

    def __str__(self):
        return str(self.title) if self.title else str(_("Untitled Document"))

    def save(self, *args, **kwargs):
        """Write content to object storage only if _content has changed."""
        super().save(*args, **kwargs)

        if self._content:
            file_key = self.file_key
            bytes_content = self._content.encode("utf-8")

            # Use Google Cloud Storage client to check if the object exists
            client = get_storage_client()
            bucket = client.bucket(settings.GCS_DOCS_BUCKET_NAME)
            blob = bucket.blob(file_key)

            # Check if the blob exists and compare its hash
            if not blob.exists() or blob.etag != hashlib.md5(bytes_content).hexdigest():
                blob.upload_from_string(bytes_content)

    @property
    def key_base(self):
        """Key base of the location where the document is stored in object storage."""
        if not self.pk:
            raise RuntimeError("The document instance must be saved before requesting a storage key.")
        today = datetime.today()
        date_path = f"year={today.year}/month={today.month:02d}/day={today.day:02d}"
        if self.creator:
            return f"user={str(self.creator.uuid)}/{date_path}/{self.pk}"
        return f"{date_path}/{self.pk}"

    @property
    def file_key(self):
        """Key of the object storage file to which the document content is stored"""
        return f"{self.key_base}/file"

    @property
    def content(self):
        """Return the json content from object storage if available"""
        if self._content is None and self.id:
            try:
                response = self.get_content_response()
            except (FileNotFoundError, ClientError) as e:
                logger.warning(
                    "Document %s has no file in storage at %s: %s",
                    self.id,
                    self.file_key,
                    e,
                )
            else:
                self._content = response["Body"].read().decode("utf-8")
        return self._content

    @content.setter
    def content(self, content):
        """Cache the content, don't write to object storage yet"""
        if not isinstance(content, str):
            raise ValueError("content should be a string.")

        self._content = content

    def get_content_response(self, version_id=""):
        """Get the content in a specific version of the document"""
        if not version_id:
            client = get_storage_client()
            bucket = client.bucket(settings.GCS_DOCS_BUCKET_NAME)
            blob = bucket.blob(self.file_key)
            if not blob.exists():
                raise FileNotFoundError(f"Blob {self.file_key} not found in bucket {settings.GCS_DOCS_BUCKET_NAME}")
            import io

            return {"Body": io.BytesIO(blob.download_as_bytes())}
        else:
            client = get_storage_client()
            bucket = client.bucket(settings.GCS_DOCS_BUCKET_NAME)
            blob = bucket.blob(self.file_key, generation=version_id)
            if not blob.exists():
                raise FileNotFoundError(f"Blob {self.file_key} with version {version_id} not found")
            import io

            return {"Body": io.BytesIO(blob.download_as_bytes())}

    def get_versions_slice(self, from_version_id="", min_datetime=None, page_size=None):
        """Get document versions from object storage with pagination and starting conditions"""
        if settings.USE_S3_MEDIA:
            # /!\ Trick here /!\
            # The "KeyMarker" and "VersionIdMarker" fields must either be both set or both not set.
            # The error we get otherwise is not helpful at all.
            markers = {}
            if from_version_id:
                markers.update({"KeyMarker": self.file_key, "VersionIdMarker": from_version_id})

            real_page_size = (
                min(page_size, settings.DOCUMENT_VERSIONS_PAGE_SIZE) if page_size else settings.DOCUMENT_VERSIONS_PAGE_SIZE
            )

            response = default_storage.connection.meta.client.list_object_versions(
                Bucket=default_storage.bucket_name,
                Prefix=self.file_key,
                # compensate the latest version that we exclude below and get one more to
                # know if there are more pages
                MaxKeys=real_page_size + 2,
                **markers,
            )

            min_last_modified = min_datetime or self.created_at
            versions = [
                {
                    key_snake: version[key_camel]
                    for key_snake, key_camel in [
                        ("etag", "ETag"),
                        ("is_latest", "IsLatest"),
                        ("last_modified", "LastModified"),
                        ("version_id", "VersionId"),
                    ]
                }
                for version in response.get("Versions", [])
                if version["LastModified"] >= min_last_modified and version["IsLatest"] is False
            ]
            results = versions[:real_page_size]

            count = len(results)
            if count == len(versions):
                is_truncated = False
                next_version_id_marker = ""
            else:
                is_truncated = True
                next_version_id_marker = versions[count - 1]["version_id"]

            return {
                "next_version_id_marker": next_version_id_marker,
                "is_truncated": is_truncated,
                "versions": results,
                "count": count,
            }
        
        elif settings.USE_GCS_MEDIA:
            # Use GCS client for versioning
            client = get_storage_client()
            bucket = client.bucket(settings.GCS_DOCS_BUCKET_NAME)
            
            real_page_size = (
                min(page_size, settings.DOCUMENT_VERSIONS_PAGE_SIZE) if page_size else settings.DOCUMENT_VERSIONS_PAGE_SIZE
            )
            
            min_last_modified = min_datetime or self.created_at
            
            # List all generations (versions) of this blob
            try:
                generations = list(bucket.list_blobs(prefix=self.file_key, versions=True))
            except Exception as e:
                logger.error(f"Error listing GCS generations for {self.file_key}: {e}")
                return {
                    "next_version_id_marker": "",
                    "is_truncated": False,
                    "versions": [],
                    "count": 0,
                }
            
            versions = []
            for gen in sorted(generations, key=lambda x: x.generation or 0, reverse=True):
                # Skip the latest version (current) and versions before min_datetime
                if gen.generation and gen.time_created:
                    if gen.time_created.replace(tzinfo=None) >= min_last_modified.replace(tzinfo=None):
                        versions.append({
                            "etag": gen.etag.strip('"'),
                            "is_latest": False,
                            "last_modified": gen.time_created,
                            "version_id": str(gen.generation),
                        })
                        if len(versions) >= real_page_size + 1:
                            break
            
            results = versions[:real_page_size]
            
            count = len(results)
            if count == len(versions) or len(versions) <= real_page_size:
                is_truncated = False
                next_version_id_marker = ""
            else:
                is_truncated = True
                next_version_id_marker = versions[count - 1]["version_id"]
            
            return {
                "next_version_id_marker": next_version_id_marker,
                "is_truncated": is_truncated,
                "versions": results,
                "count": count,
            }
        
        # No S3 or GCS enabled
        return {
            "next_version_id_marker": "",
            "is_truncated": False,
            "versions": [],
            "count": 0,
        }

    def delete_version(self, version_id):
        """Delete a version from object storage given its version id"""
        if settings.USE_S3_MEDIA:
            return default_storage.connection.meta.client.delete_object(
                Bucket=default_storage.bucket_name, Key=self.file_key, VersionId=version_id
            )
        elif settings.USE_GCS_MEDIA:
            # Use GCS client to delete the specific generation
            client = get_storage_client()
            bucket = client.bucket(settings.GCS_DOCS_BUCKET_NAME)
            blob = bucket.blob(self.file_key, generation=version_id)
            
            try:
                blob.delete()
                return {"ResponseMetadata": {"HTTPStatusCode": 204}}
            except Exception as e:
                logger.error(f"Error deleting GCS generation {version_id} for {self.file_key}: {e}")
                return {"ResponseMetadata": {"HTTPStatusCode": 404}}
        
        # No S3 or GCS enabled
        return {"ResponseMetadata": {"HTTPStatusCode": 404}}

    def get_nb_accesses_cache_key(self):
        """Generate a unique cache key for each document."""
        return f"document_{self.id!s}_nb_accesses"

    def get_nb_accesses(self):
        """
        Calculate the number of accesses:
        - directly attached to the document
        - attached to any of the document's ancestors
        """
        cache_key = self.get_nb_accesses_cache_key()
        nb_accesses = cache.get(cache_key)

        if nb_accesses is None:
            nb_accesses = (
                DocumentAccess.objects.filter(document=self).count(),
                DocumentAccess.objects.filter(
                    document__path=Left(models.Value(self.path), Length("document__path")),
                    document__ancestors_deleted_at__isnull=True,
                ).count(),
            )
            cache.set(cache_key, nb_accesses)

        return nb_accesses

    @property
    def nb_accesses_direct(self):
        """Returns the number of accesses related to the document or one of its ancestors."""
        return self.get_nb_accesses()[0]

    @property
    def nb_accesses_ancestors(self):
        """Returns the number of accesses related to the document or one of its ancestors."""
        return self.get_nb_accesses()[1]

    def invalidate_nb_accesses_cache(self):
        """
        Invalidate the cache for number of accesses, including on affected descendants.
        Args:
            path: can optionally be passed as argument (useful when invalidating cache for a
                document we just deleted)
        """

        for document in Document.objects.filter(path__startswith=self.path).only("id"):
            cache_key = document.get_nb_accesses_cache_key()
            cache.delete(cache_key)

    def get_roles(self, user):
        """Return the roles a user has on a document."""
        if not user.is_authenticated:
            return []

        try:
            roles = self.user_roles or []
        except AttributeError:
            try:
                # team_ids = Membership.objects.filter(user=user).values_list("team_id", flat=True)
                team_ids = list(Membership.objects.filter(user=user).values_list("team_id", flat=True))

                roles = DocumentAccess.objects.filter(
                    models.Q(user=user) | models.Q(team__in=team_ids),
                    document__path=Left(models.Value(self.path), Length("document__path")),
                ).values_list("role", flat=True)
            except (models.ObjectDoesNotExist, IndexError):
                roles = []
        return roles

    def get_links_definitions(self, ancestors_links):
        """Get links reach/role definitions for the current document and its ancestors."""

        links_definitions = defaultdict(set)
        links_definitions[self.link_reach].add(self.link_role)

        # Merge ancestor link definitions
        for ancestor in ancestors_links:
            links_definitions[ancestor["link_reach"]].add(ancestor["link_role"])

        return dict(links_definitions)  # Convert defaultdict back to a normal dict

    def compute_ancestors_links(self, user):
        """
        Compute the ancestors links for the current document up to the highest readable ancestor.
        """
        ancestors = (
            (self.get_ancestors() | self._meta.model.objects.filter(pk=self.pk))
            .filter(ancestors_deleted_at__isnull=True)
            .order_by("path")
        )
        highest_readable = ancestors.readable_per_se(user).only("depth").first()

        if highest_readable is None:
            return []

        ancestors_links = []
        paths_links_mapping = {}
        for ancestor in ancestors.filter(depth__gte=highest_readable.depth):
            ancestors_links.append({"link_reach": ancestor.link_reach, "link_role": ancestor.link_role})
            paths_links_mapping[ancestor.path] = ancestors_links.copy()

        ancestors_links = paths_links_mapping.get(self.path[: -self.steplen], [])

        return ancestors_links

    def get_abilities(self, user, ancestors_links=None):
        """
        Compute and return abilities for a given user on the document.
        """
        if self.depth <= 1 or getattr(self, "is_highest_ancestor_for_user", False):
            ancestors_links = []
        elif ancestors_links is None:
            ancestors_links = self.compute_ancestors_links(user=user)

        roles = set(self.get_roles(user))  # at this point only roles based on specific access

        # Characteristics that are based only on specific access
        is_owner = RoleChoices.OWNER in roles
        is_deleted = self.ancestors_deleted_at and not is_owner
        is_owner_or_admin = (is_owner or RoleChoices.ADMIN in roles) and not is_deleted

        # Compute access roles before adding link roles because we don't
        # want anonymous users to access versions (we wouldn't know from
        # which date to allow them anyway)
        # Anonymous users should also not see document accesses
        has_access_role = bool(roles) and not is_deleted
        can_update_from_access = (is_owner_or_admin or RoleChoices.EDITOR in roles) and not is_deleted

        # Add roles provided by the document link, taking into account its ancestors
        links_definitions = self.get_links_definitions(ancestors_links)
        public_roles = links_definitions.get(LinkReachChoices.PUBLIC, set())
        authenticated_roles = (
            links_definitions.get(LinkReachChoices.AUTHENTICATED, set()) if user.is_authenticated else set()
        )
        roles = roles | public_roles | authenticated_roles

        can_get = bool(roles) and not is_deleted
        can_update = (is_owner_or_admin or RoleChoices.EDITOR in roles) and not is_deleted
        ai_allow_reach_from = settings.AI_ALLOW_REACH_FROM
        ai_access = any(
            [
                ai_allow_reach_from == LinkReachChoices.PUBLIC and can_update,
                ai_allow_reach_from == LinkReachChoices.AUTHENTICATED and user.is_authenticated and can_update,
                ai_allow_reach_from == LinkReachChoices.RESTRICTED and can_update_from_access,
            ]
        )

        return {
            "accesses_manage": is_owner_or_admin,
            "accesses_view": has_access_role,
            "ai_transform": ai_access,
            "ai_translate": ai_access,
            "attachment_upload": can_update,
            "children_list": can_get,
            "children_create": can_update and user.is_authenticated,
            "collaboration_auth": can_get,
            "cors_proxy": can_get,
            "descendants": can_get,
            "destroy": is_owner,
            "duplicate": can_get,
            "favorite": can_get and user.is_authenticated,
            "link_configuration": is_owner_or_admin,
            "invite_owner": is_owner,
            "move": is_owner_or_admin and not self.ancestors_deleted_at,
            "partial_update": can_update,
            "restore": is_owner,
            "retrieve": can_get,
            "media_auth": can_get,
            "link_select_options": LinkReachChoices.get_select_options(ancestors_links),
            "tree": can_get,
            "update": can_update,
            "versions_destroy": is_owner_or_admin,
            "versions_list": has_access_role,
            "versions_retrieve": has_access_role,
        }

    def send_email(self, subject, emails, context=None, language=None):
        """Generate and send email from a template."""
        context = context or {}
        domain = Site.objects.get_current().domain
        language = language or get_language()
        context.update(
            {
                "brandname": settings.EMAIL_BRAND_NAME,
                "document": self,
                "domain": domain,
                "link": f"{domain}/docs/{self.id}/",
                "document_title": self.title or str(_("Untitled Document")),
                "logo_img": settings.EMAIL_LOGO_IMG,
            }
        )

        with override(language):
            msg_html = render_to_string("mail/html/invitation.html", context)
            msg_plain = render_to_string("mail/text/invitation.txt", context)
            subject = str(subject)  # Force translation

            try:
                send_mail(
                    subject.capitalize(),
                    msg_plain,
                    settings.EMAIL_FROM,
                    emails,
                    html_message=msg_html,
                    fail_silently=False,
                )
            except smtplib.SMTPException as exception:
                logger.error("invitation to %s was not sent: %s", emails, exception)

    def send_invitation_email(self, email, role, sender, language=None):
        """Method allowing a user to send an email invitation to another user for a document."""
        language = language or get_language()
        role = RoleChoices(role).label
        sender_name = sender.full_name or sender.email
        sender_name_email = f"{sender.full_name:s} ({sender.email})" if sender.full_name else sender.email

        with override(language):
            context = {
                "title": _("{name} shared a document with you!").format(name=sender_name),
                "message": _('{name} invited you with the role "{role}" on the following document:').format(
                    name=sender_name_email, role=role.lower()
                ),
            }
            subject = (
                context["title"]
                if not self.title
                else _("{name} shared a document with you: {title}").format(name=sender_name, title=self.title)
            )

        self.send_email(subject, [email], context, language)

    @transaction.atomic
    def soft_delete(self):
        """
        Soft delete the document, marking the deletion on descendants.
        We still keep the .delete() method untouched for programmatic purposes.
        """
        if (
            self._meta.model.objects.filter(
                models.Q(deleted_at__isnull=False) | models.Q(ancestors_deleted_at__isnull=False),
                pk=self.pk,
            ).exists()
            or self.get_ancestors().filter(deleted_at__isnull=False).exists()
        ):
            raise RuntimeError("This document is already deleted or has deleted ancestors.")

        self.ancestors_deleted_at = self.deleted_at = timezone.now()
        self.save()
        self.invalidate_nb_accesses_cache()

        if self.depth > 1:
            self._meta.model.objects.filter(pk=self.get_parent().pk).update(numchild=models.F("numchild") - 1)

        # Mark all descendants as soft deleted
        self.get_descendants().filter(ancestors_deleted_at__isnull=True).update(
            ancestors_deleted_at=self.ancestors_deleted_at
        )

    @transaction.atomic
    def restore(self):
        """Cancelling a soft delete with checks."""
        # This should not happen
        if self._meta.model.objects.filter(pk=self.pk, deleted_at__isnull=True).exists():
            raise RuntimeError("This document is not deleted.")

        if self.deleted_at < get_trashbin_cutoff():
            raise RuntimeError("This document was permanently deleted and cannot be restored.")

        # save the current deleted_at value to exclude it from the descendants update
        current_deleted_at = self.deleted_at

        # Restore the current document
        self.deleted_at = None

        # Calculate the minimum `deleted_at` among all ancestors
        ancestors_deleted_at = (
            self.get_ancestors()
            .filter(deleted_at__isnull=False)
            .order_by("deleted_at")
            .values_list("deleted_at", flat=True)
            .first()
        )
        self.ancestors_deleted_at = ancestors_deleted_at
        self.save(update_fields=["deleted_at", "ancestors_deleted_at"])
        self.invalidate_nb_accesses_cache()

        self.get_descendants().exclude(
            models.Q(deleted_at__isnull=False) | models.Q(ancestors_deleted_at__lt=current_deleted_at)
        ).update(ancestors_deleted_at=self.ancestors_deleted_at)

        if self.depth > 1:
            self._meta.model.objects.filter(pk=self.get_parent().pk).update(numchild=models.F("numchild") + 1)


class LinkTrace(BaseModel):
    """
    Relation model to trace accesses to a document via a link by a logged-in user.
    This is necessary to show the document in the user's list of documents even
    though the user does not have a role on the document.
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="link_traces",
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="link_traces")

    class Meta:
        db_table = "impress_link_trace"
        verbose_name = _("Document/user link trace")
        verbose_name_plural = _("Document/user link traces")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document"],
                name="unique_link_trace_document_user",
                violation_error_message=_("A link trace already exists for this document/user."),
            ),
        ]

    def __str__(self):
        return f"{self.user!s} trace on document {self.document!s}"


class DocumentFavorite(BaseModel):
    """Relation model to store a user's favorite documents."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="favorited_by_users",
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="favorite_documents")

    class Meta:
        db_table = "impress_document_favorite"
        verbose_name = _("Document favorite")
        verbose_name_plural = _("Document favorites")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document"],
                name="unique_document_favorite_user",
                violation_error_message=_(
                    "This document is already targeted by a favorite relation instance for the same user."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.user!s} favorite on document {self.document!s}"


class DocumentAccess(BaseAccess):
    """Relation model to give access to a document for a user or a team with a role."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="accesses",
    )

    class Meta:
        db_table = "impress_document_access"
        ordering = ("-created_at",)
        verbose_name = _("Document/user relation")
        verbose_name_plural = _("Document/user relations")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document"],
                condition=models.Q(user__isnull=False),  # Exclude null users
                name="unique_document_user",
                violation_error_message=_("This user is already in this document."),
            ),
            models.UniqueConstraint(
                fields=["team", "document"],
                condition=models.Q(team__gt=""),  # Exclude empty string teams
                name="unique_document_team",
                violation_error_message=_("This team is already in this document."),
            ),
            models.CheckConstraint(
                check=models.Q(user__isnull=False, team="") | models.Q(user__isnull=True, team__gt=""),
                name="check_document_access_either_user_or_team",
                violation_error_message=_("Either user or team must be set, not both."),
            ),
        ]

    def __str__(self):
        return f"{self.user!s} is {self.role:s} in document {self.document!s}"

    def save(self, *args, **kwargs):
        """Override save to clear the document's cache for number of accesses."""
        super().save(*args, **kwargs)
        self.document.invalidate_nb_accesses_cache()

    def delete(self, *args, **kwargs):
        """Override delete to clear the document's cache for number of accesses."""
        super().delete(*args, **kwargs)
        self.document.invalidate_nb_accesses_cache()

    def get_abilities(self, user):
        """
        Compute and return abilities for a given user on the document access.
        """
        roles = self._get_roles(self.document, user)
        is_owner_or_admin = bool(set(roles).intersection(set(PRIVILEGED_ROLES)))
        if self.role == RoleChoices.OWNER:
            can_delete = (
                RoleChoices.OWNER in roles and self.document.accesses.filter(role=RoleChoices.OWNER).count() > 1
            )
            set_role_to = [RoleChoices.ADMIN, RoleChoices.EDITOR, RoleChoices.READER] if can_delete else []
        else:
            can_delete = is_owner_or_admin
            set_role_to = []
            if RoleChoices.OWNER in roles:
                set_role_to.append(RoleChoices.OWNER)
            if is_owner_or_admin:
                set_role_to.extend([RoleChoices.ADMIN, RoleChoices.EDITOR, RoleChoices.READER])

        # Remove the current role as we don't want to propose it as an option
        with contextlib.suppress(ValueError):
            set_role_to.remove(self.role)

        return {
            "destroy": can_delete,
            "update": bool(set_role_to) and is_owner_or_admin,
            "partial_update": bool(set_role_to) and is_owner_or_admin,
            "retrieve": self.user and self.user.id == user.id or is_owner_or_admin,
            "set_role_to": set_role_to,
        }


class Template(BaseModel):
    """HTML and CSS code used for formatting the print around the MarkDown body."""

    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    code = models.TextField(_("code"), blank=True)
    css = models.TextField(_("css"), blank=True)
    is_public = models.BooleanField(
        _("public"),
        default=False,
        help_text=_("Whether this template is public for anyone to use."),
    )

    class Meta:
        db_table = "impress_template"
        ordering = ("title",)
        verbose_name = _("Template")
        verbose_name_plural = _("Templates")

    def __str__(self):
        return self.title

    def get_roles(self, user):
        """Return the roles a user has on a resource as an iterable."""
        if not user.is_authenticated:
            return []

        try:
            roles = self.user_roles or []
        except AttributeError:
            try:
                roles = self.accesses.filter(
                    models.Q(user=user) | models.Q(team__in=user.teams),
                ).values_list("role", flat=True)
            except (models.ObjectDoesNotExist, IndexError):
                roles = []
        return roles

    def get_abilities(self, user):
        """
        Compute and return abilities for a given user on the template.
        """
        roles = self.get_roles(user)
        is_owner_or_admin = bool(set(roles).intersection({RoleChoices.OWNER, RoleChoices.ADMIN}))
        can_get = self.is_public or bool(roles)
        can_update = is_owner_or_admin or RoleChoices.EDITOR in roles

        return {
            "destroy": RoleChoices.OWNER in roles,
            "generate_document": can_get,
            "accesses_manage": is_owner_or_admin,
            "update": can_update,
            "partial_update": can_update,
            "retrieve": can_get,
        }


class TemplateAccess(BaseAccess):
    """Relation model to give access to a template for a user or a team with a role."""

    template = models.ForeignKey(
        Template,
        on_delete=models.CASCADE,
        related_name="accesses",
    )

    class Meta:
        db_table = "impress_template_access"
        ordering = ("-created_at",)
        verbose_name = _("Template/user relation")
        verbose_name_plural = _("Template/user relations")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "template"],
                condition=models.Q(user__isnull=False),  # Exclude null users
                name="unique_template_user",
                violation_error_message=_("This user is already in this template."),
            ),
            models.UniqueConstraint(
                fields=["team", "template"],
                condition=models.Q(team__gt=""),  # Exclude empty string teams
                name="unique_template_team",
                violation_error_message=_("This team is already in this template."),
            ),
            models.CheckConstraint(
                check=models.Q(user__isnull=False, team="") | models.Q(user__isnull=True, team__gt=""),
                name="check_template_access_either_user_or_team",
                violation_error_message=_("Either user or team must be set, not both."),
            ),
        ]

    def __str__(self):
        return f"{self.user!s} is {self.role:s} in template {self.template!s}"

    def get_abilities(self, user):
        """
        Compute and return abilities for a given user on the template access.
        """
        return self._get_abilities(self.template, user)


class Invitation(BaseModel):
    """User invitation to a document."""

    email = models.EmailField(_("email address"), null=False, blank=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.READER)
    issuer = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="invitations",
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "impress_invitation"
        verbose_name = _("Document invitation")
        verbose_name_plural = _("Document invitations")
        constraints = [models.UniqueConstraint(fields=["email", "document"], name="email_and_document_unique_together")]

    def __str__(self):
        return f"{self.email} invited to {self.document}"

    def clean(self):
        """Validate fields."""
        super().clean()

        # Check if an identity already exists for the provided email
        if CustomUser.objects.filter(email=self.email).exists() and not settings.OIDC_ALLOW_DUPLICATE_EMAILS:
            raise ValidationError({"email": [_("This email is already associated to a registered user.")]})

    @property
    def is_expired(self):
        """Calculate if invitation is still valid or has expired."""
        if not self.created_at:
            return None

        validity_duration = timedelta(seconds=settings.INVITATION_VALIDITY_DURATION)
        return timezone.now() > (self.created_at + validity_duration)

    def get_abilities(self, user):
        """Compute and return abilities for a given user."""
        roles = []

        if user.is_authenticated:
            # team_ids = Membership.objects.filter(user=user).values_list("team_id", flat=True)
            team_ids = list(Membership.objects.filter(user=user).values_list("team_id", flat=True))

            try:
                roles = self.user_roles or []
            except AttributeError:
                try:
                    roles = self.document.accesses.filter(
                        models.Q(user=user) | models.Q(team__in=team_ids),
                    ).values_list("role", flat=True)
                except (self._meta.model.DoesNotExist, IndexError):
                    roles = []

        is_admin_or_owner = bool(set(roles).intersection({RoleChoices.OWNER, RoleChoices.ADMIN}))

        return {
            "destroy": is_admin_or_owner,
            "update": is_admin_or_owner,
            "partial_update": is_admin_or_owner,
            "retrieve": is_admin_or_owner,
        }
