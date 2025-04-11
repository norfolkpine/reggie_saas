from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from agno.tools.confluence import ConfluenceTools
from agno.tools.slack import SlackTools
from agno.tools.telegram import TelegramTools
from agno.tools.gmail import GmailTools
from apps.reggie.agents.tools.custom_whatsapp import WhatsAppTools
from django.db import models
from datetime import datetime

from apps.integrations.models import Integration
from apps.integrations.serializers import IntegrationSerializer


class IntegrationViewSet(viewsets.ModelViewSet):
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Integration.objects.filter(
            models.Q(user=user) |
            models.Q(team__in=user.teams.all())
        )

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        integration = self.get_object()

        if integration.integration_type == 'confluence':
            confluence_config = integration.confluenceintegration
            try:
                tools = ConfluenceTools(
                    url=confluence_config.url,
                    username=confluence_config.username,
                    api_key=confluence_config.api_key
                )
                # Test connection
                spaces = tools.get_all_space_detail()
                return Response({'status': 'success', 'spaces': spaces})
            except Exception as e:
                return Response(
                    {'status': 'error', 'message': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif integration.integration_type == 'slack':
            slack_config = integration.slackintegration
            try:
                tools = SlackTools(token=slack_config.bot_token)
                # Test connection
                channels = tools.list_channels()
                return Response({'status': 'success', 'channels': channels})
            except Exception as e:
                return Response(
                    {'status': 'error', 'message': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif integration.integration_type == 'whatsapp':
            whatsapp_config = integration.whatsappintegration
            try:
                tools = WhatsAppTools(
                    account_sid=whatsapp_config.account_sid,
                    auth_token=whatsapp_config.auth_token,
                    phone_number=whatsapp_config.phone_number
                )
                # Test connection by getting account status
                status = tools.get_account_status()
                return Response({'status': 'success', 'account_status': status})
            except Exception as e:
                return Response(
                    {'status': 'error', 'message': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif integration.integration_type == 'telegram':
            telegram_config = integration.telegramintegration
            try:
                tools = TelegramTools(bot_token=telegram_config.bot_token)
                # Test connection by getting bot info
                bot_info = tools.get_bot_info()
                # Verify chat_id is valid
                chat_info = tools.get_chat_info(telegram_config.chat_id)
                return Response({
                    'status': 'success',
                    'bot_info': bot_info,
                    'chat_info': chat_info
                })
            except Exception as e:
                return Response(
                    {'status': 'error', 'message': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif integration.integration_type == 'gmail':
            gmail_config = integration.gmailintegration
            try:
                # Check if token needs refresh
                if gmail_config.token_expiry <= datetime.now():
                    tools = GmailTools(
                        refresh_token=gmail_config.refresh_token,
                        email=gmail_config.email
                    )
                    # Refresh token
                    new_tokens = tools.refresh_access_token()
                    gmail_config.access_token = new_tokens['access_token']
                    gmail_config.token_expiry = new_tokens['expiry']
                    gmail_config.save()

                tools = GmailTools(
                    access_token=gmail_config.access_token,
                    email=gmail_config.email
                )
                # Test connection by getting user profile
                profile = tools.get_user_profile()
                return Response({
                    'status': 'success',
                    'profile': profile,
                    'token_expiry': gmail_config.token_expiry.isoformat()
                })
            except Exception as e:
                return Response(
                    {'status': 'error', 'message': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(
            {'status': 'error', 'message': 'Unsupported integration type'},
            status=status.HTTP_400_BAD_REQUEST
        )
