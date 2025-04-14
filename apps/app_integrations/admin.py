from django.contrib import admin

from .models import ConnectedApp, SupportedApp


@admin.register(ConnectedApp)
class ConnectedAppAdmin(admin.ModelAdmin):
    list_display = ("user", "app", "expires_at", "created_at")
    search_fields = ("user__email", "app")


@admin.register(SupportedApp)
class SupportedAppAdmin(admin.ModelAdmin):
    list_display = ("title", "key", "description", "icon_url")
    search_fields = ("title", "key")
    list_filter = ("key",)
