from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from agno.tools.confluence import ConfluenceTools
from agno.tools.slack import SlackTools
from django.db import models

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

        return Response(
            {'status': 'error', 'message': 'Unsupported integration type'},
            status=status.HTTP_400_BAD_REQUEST
        )
