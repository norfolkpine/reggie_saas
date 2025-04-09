from django.conf import settings
from django.db import models


class AbstractIntegration(models.Model):
    """Base class for any integration service (e.g., Slack, Jira)."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)s_integrations"
    )
    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="%(class)s_integrations", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
