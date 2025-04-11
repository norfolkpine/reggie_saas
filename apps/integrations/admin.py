from django.contrib import admin
from .models import (
    Integration,
    ConfluenceIntegration,
    SlackIntegration,
    WhatsAppIntegration,
    TelegramIntegration,
    GmailIntegration
)

class ConfluenceIntegrationInline(admin.StackedInline):
    model = ConfluenceIntegration
    extra = 0
    fields = ('url', 'username', 'space_key')

class SlackIntegrationInline(admin.StackedInline):
    model = SlackIntegration
    extra = 0
    fields = ('workspace_id', 'channels')

class WhatsAppIntegrationInline(admin.StackedInline):
    model = WhatsAppIntegration
    extra = 0
    fields = ('phone_number',)

class TelegramIntegrationInline(admin.StackedInline):
    model = TelegramIntegration
    extra = 0
    fields = ('chat_id',)

class GmailIntegrationInline(admin.StackedInline):
    model = GmailIntegration
    extra = 0
    fields = ('email', 'token_expiry')

@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'integration_type', 'is_active', 'team', 'user', 'created_at')
    list_filter = ('integration_type', 'is_active', 'created_at')
    search_fields = ('name', 'team__name', 'user__email')
    date_hierarchy = 'created_at'
    inlines = [
        ConfluenceIntegrationInline,
        SlackIntegrationInline,
        WhatsAppIntegrationInline,
        TelegramIntegrationInline,
        GmailIntegrationInline,
    ]

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        if obj.integration_type == 'confluence':
            return [ConfluenceIntegrationInline(self.model, self.admin_site)]
        elif obj.integration_type == 'slack':
            return [SlackIntegrationInline(self.model, self.admin_site)]
        elif obj.integration_type == 'whatsapp':
            return [WhatsAppIntegrationInline(self.model, self.admin_site)]
        elif obj.integration_type == 'telegram':
            return [TelegramIntegrationInline(self.model, self.admin_site)]
        elif obj.integration_type == 'gmail':
            return [GmailIntegrationInline(self.model, self.admin_site)]
        return []
