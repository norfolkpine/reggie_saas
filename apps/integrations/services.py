from typing import List
from django.db import models
from agno.agent import Agent
# from agno.tools.base import BaseTool
from .models import Integration

class IntegrationManager:
    def __init__(self, user=None, team=None):
        self.user = user
        self.team = team

    def get_active_integrations(self) -> List[Integration]:
        """Get all active integrations for the user/team."""
        query = models.Q(is_active=True)
        if self.user:
            query |= models.Q(user=self.user)
        if self.team:
            query |= models.Q(team=self.team)
        return Integration.objects.filter(query)

    # def get_tools_for_agent(self) -> List[BaseTool]:
    #     """Get all tools from active integrations."""
    #     tools = []
    #     integrations = self.get_active_integrations()

    #     for integration in integrations:
    #         if integration.integration_type == 'confluence':
    #             config = integration.confluenceintegration
    #             tools.append(ConfluenceTools(
    #                 url=config.url,
    #                 username=config.username,
    #                 api_key=config.api_key
    #             ))
    #         elif integration.integration_type == 'slack':
    #             config = integration.slackintegration
    #             tools.append(SlackTools(token=config.bot_token))
    #         # Add other integration types here

    #     return tools