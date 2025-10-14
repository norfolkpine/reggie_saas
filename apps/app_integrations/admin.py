from django.contrib import admin

from .models import ConnectedApp, SupportedApp, NangoConnection


@admin.register(ConnectedApp)
class ConnectedAppAdmin(admin.ModelAdmin):
    list_display = ("user", "app", "expires_at", "created_at")
    search_fields = ("user__email", "app__title", "app__key")
    list_filter = ("app",)
    autocomplete_fields = ("app", "user")


@admin.register(SupportedApp)
class SupportedAppAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "description", "icon_url")
    search_fields = ("title", "key")
    list_filter = ("key",)


@admin.register(NangoConnection)
class NangoConnectionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "connection_id", "provider", "subdomain", "cloud_id", "created_at")
    search_fields = ("user_id", "connection_id", "provider", "subdomain", "cloud_id")
    list_filter = ("provider", "created_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {
            "fields": ("user_id", "connection_id", "provider")
        }),
        ("JIRA Configuration", {
            "fields": ("base_url", "cloud_id", "account_id", "subdomain"),
            "classes": ("collapse",)
        }),
        ("Connection Data", {
            "fields": ("config", "metadata"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        })
    )
