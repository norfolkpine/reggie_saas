"""Admin classes and registrations for core app."""

from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from apps.users.models import CustomUser
from . import models


class TemplateAccessInline(admin.TabularInline):
    """Inline admin class for template accesses."""

    autocomplete_fields = ["user"]
    model = models.TemplateAccess
    extra = 0


@admin.register(models.Template)
class TemplateAdmin(admin.ModelAdmin):
    """Template admin interface declaration."""

    inlines = (TemplateAccessInline,)


class DocumentAccessInline(admin.TabularInline):
    """Inline admin class for template accesses."""

    autocomplete_fields = ["user"]
    model = models.DocumentAccess
    extra = 0


@admin.register(models.Document)
class DocumentAdmin(TreeAdmin):
    """Document admin interface declaration."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "id",
                    "title",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "creator",
                    "link_reach",
                    "link_role",
                )
            },
        ),
        (
            _("Tree structure"),
            {
                "fields": (
                    "path",
                    "depth",
                    "numchild",
                    "duplicated_from",
                    "attachments",
                )
            },
        ),
    )
    form = movenodeform_factory(models.Document)
    inlines = (DocumentAccessInline,)
    list_display = (
        "id",
        "title",
        "link_reach",
        "link_role",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "attachments",
        "creator",
        "depth",
        "duplicated_from",
        "id",
        "numchild",
        "path",
    )
    search_fields = ("id", "title")


@admin.register(models.Invitation)
class InvitationAdmin(admin.ModelAdmin):
    """Admin interface to handle invitations."""

    fields = (
        "email",
        "document",
        "role",
        "created_at",
        "issuer",
    )
    readonly_fields = (
        "created_at",
        "is_expired",
        "issuer",
    )
    list_display = (
        "email",
        "document",
        "created_at",
        "is_expired",
    )

    def save_model(self, request, obj, form, change):
        obj.issuer = request.user
        obj.save()


@admin.register(models.DocumentFavorite)
class DocumentFavoriteAdmin(admin.ModelAdmin):
    """Admin interface for document favorites."""

    list_display = (
        "id",
        "document",
        "user",
        "created_at",
        "updated_at",
    )
    search_fields = ("document__title", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(models.LinkTrace)
class LinkTraceAdmin(admin.ModelAdmin):
    """Admin interface for link traces."""

    list_display = (
        "id",
        "document",
        "user",
        "created_at",
        "updated_at",
    )
    search_fields = ("document__title", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(models.TemplateAccess)
class TemplateAccessAdmin(admin.ModelAdmin):
    """Admin interface for template access."""

    list_display = (
        "id",
        "template",
        "user",
        "team",
        "role",
        "created_at",
        "updated_at",
    )
    search_fields = ("template__title", "user__email", "team")
    readonly_fields = ("created_at", "updated_at")
