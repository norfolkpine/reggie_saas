from rest_framework import serializers
from .models import (
    Integration, ConfluenceIntegration, SlackIntegration,
    WhatsAppIntegration, TelegramIntegration, GmailIntegration
)

class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = ['id', 'name', 'integration_type', 'is_active', 'team', 'user', 'created_at']
        read_only_fields = ['created_at']

class ConfluenceIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfluenceIntegration
        fields = ['url', 'username', 'api_key', 'space_key']
        extra_kwargs = {'api_key': {'write_only': True}}

class SlackIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlackIntegration
        fields = ['workspace_id', 'channels']
        read_only_fields = ['workspace_id']