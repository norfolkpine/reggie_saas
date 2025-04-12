from django.contrib import admin

from .models import ConnectedApp


@admin.register(ConnectedApp)
class ConnectedAppAdmin(admin.ModelAdmin):
    list_display = ("user", "app", "expires_at", "created_at")
    search_fields = ("user__email", "app")
