from django.db import models
from django.conf import settings
from apps.teams.models import Team
from .fields import EncryptedField

class Integration(models.Model):
    INTEGRATION_TYPES = [
        ('confluence', 'Confluence'),
        ('slack', 'Slack'),
        ('whatsapp', 'WhatsApp'),
        ('telegram', 'Telegram'),
        ('gmail', 'Gmail'),
    ]

    name = models.CharField(max_length=255)
    integration_type = models.CharField(max_length=50, choices=INTEGRATION_TYPES)
    is_active = models.BooleanField(default=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('integration_type', 'team'), ('integration_type', 'user')]

    def __str__(self):
        return f"{self.name} ({self.get_integration_type_display()})"

class ConfluenceIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    url = models.URLField(max_length=500)
    username = models.CharField(max_length=255)
    api_key = EncryptedField()
    space_key = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Confluence: {self.integration.name}"

class SlackIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    workspace_id = models.CharField(max_length=255)
    bot_token = EncryptedField()
    access_token = EncryptedField()
    channels = models.JSONField(default=list)

    def __str__(self):
        return f"Slack: {self.integration.name}"

class WhatsAppIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=50)
    api_key = EncryptedField()

    def __str__(self):
        return f"WhatsApp: {self.integration.name}"

class TelegramIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    bot_token = EncryptedField()
    chat_id = models.CharField(max_length=255)

    def __str__(self):
        return f"Telegram: {self.integration.name}"

class GmailIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    email = models.EmailField()
    refresh_token = EncryptedField()
    access_token = EncryptedField()
    token_expiry = models.DateTimeField()

    def __str__(self):
        return f"Gmail: {self.email}"
