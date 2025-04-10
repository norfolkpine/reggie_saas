# slack_integration/storage.py
from slack_sdk.oauth.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models import Installation

from apps.slack_integration.models import SlackWorkspace


class DjangoInstallationStore(InstallationStore):
    def save(self, installation: Installation):
        SlackWorkspace.objects.update_or_create(
            slack_team_id=installation.team_id,
            defaults={
                "slack_team_name": installation.team_name,
                "access_token": installation.bot_token,
                "bot_user_id": installation.bot_user_id,
                # You can extend this with installer_user_id, scope, etc.
            }
        )

    def find_bot(self, enterprise_id: str | None, team_id: str) -> Installation | None:
        try:
            workspace = SlackWorkspace.objects.get(slack_team_id=team_id)
            return Installation(
                team_id=workspace.slack_team_id,
                team_name=workspace.slack_team_name,
                bot_token=workspace.access_token,
                bot_user_id=workspace.bot_user_id,
            )
        except SlackWorkspace.DoesNotExist:
            return None

    def delete_bot(self, enterprise_id: str | None, team_id: str):
        SlackWorkspace.objects.filter(slack_team_id=team_id).delete()
