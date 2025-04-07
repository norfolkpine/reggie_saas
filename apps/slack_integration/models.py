# slack_integration/models.py
from django.db import models
from apps.utils.models import BaseModel
from django.conf import settings

class SlackWorkspace(BaseModel):
    team = models.ForeignKey(
        "teams.Team",  # adjust to your structure
        on_delete=models.CASCADE,
        related_name="slack_workspaces",
    )
    slack_team_id = models.CharField(max_length=255, unique=True)
    slack_team_name = models.CharField(max_length=255)
    access_token = models.CharField(max_length=255)
    bot_user_id = models.CharField(max_length=255, null=True, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.slack_team_name} ({self.slack_team_id})"
