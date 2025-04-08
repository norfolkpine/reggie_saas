from django.db import models
from django.conf import settings
from django_cryptography.fields import encrypt
from apps.teams.models import Team

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

class ConfluenceIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    url = models.URLField(max_length=500)
    username = models.CharField(max_length=255)
    api_key = encrypt(models.CharField(max_length=500))
    space_key = models.CharField(max_length=255, blank=True)

class SlackIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    workspace_id = models.CharField(max_length=255)
    bot_token = encrypt(models.CharField(max_length=500))
    access_token = encrypt(models.CharField(max_length=500))
    channels = models.JSONField(default=list)

class WhatsAppIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=50)
    api_key = encrypt(models.CharField(max_length=500))

class TelegramIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    bot_token = encrypt(models.CharField(max_length=500))
    chat_id = models.CharField(max_length=255)

class GmailIntegration(models.Model):
    integration = models.OneToOneField(Integration, on_delete=models.CASCADE)
    email = models.EmailField()
    refresh_token = encrypt(models.CharField(max_length=500))
    access_token = encrypt(models.CharField(max_length=500))
    token_expiry = models.DateTimeField()
