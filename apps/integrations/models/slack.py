from django.db import models

from .base import AbstractIntegration


class SlackIntegration(AbstractIntegration):
    team_id = models.CharField(max_length=100, unique=True)
    team_name = models.CharField(max_length=255)
    access_token = models.TextField()
    bot_user_id = models.CharField(max_length=100, blank=True, null=True)
    installed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Slack: {self.team_name} ({self.team_id})"
