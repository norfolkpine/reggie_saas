from django.contrib import admin

from .models import SlackIntegration


@admin.register(SlackIntegration)
class SlackIntegrationAdmin(admin.ModelAdmin):
    list_display = ("team_name", "team_id", "user", "created_at")
