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
        fields = ['workspace_id', 'bot_token', 'access_token', 'channels']
        extra_kwargs = {
            'bot_token': {'write_only': True},
            'access_token': {'write_only': True}
        }

class WhatsAppIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppIntegration
        fields = ['account_sid', 'auth_token', 'phone_number']
        extra_kwargs = {
            'account_sid': {'write_only': True},
            'auth_token': {'write_only': True}
        }

class TelegramIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramIntegration
        fields = ['bot_token', 'chat_id']
        extra_kwargs = {'bot_token': {'write_only': True}}

class GmailIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GmailIntegration
        fields = ['email', 'refresh_token', 'access_token', 'token_expiry']
        extra_kwargs = {
            'refresh_token': {'write_only': True},
            'access_token': {'write_only': True}
        }