# apps/slack_integration/storage.py
import logging
from logging import Logger
from typing import Optional

from slack_sdk.oauth.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models import Bot, Installation

from apps.slack_integration.models import SlackWorkspace


class DjangoInstallationStore(InstallationStore):
    """Django implementation of Slack's InstallationStore that works with existing SlackWorkspace model"""

    def __init__(self, client_id: str, logger: Optional[Logger] = None):
        self.client_id = client_id
        self._logger = logger or logging.getLogger(__name__)

    @property
    def logger(self) -> Logger:
        return self._logger

    def save(self, installation: Installation):
        """Save an installation to the database"""
        try:
            # Get team_id from custom value
            team_id = installation.get_custom_value("team_id")

            if not team_id:
                self.logger.error("Missing team_id in installation custom values, cannot save installation")
                return

            # Prepare data for the SlackWorkspace model
            workspace_data = {
                "slack_team_name": installation.team_name,
                "access_token": installation.bot_token,  # Map to your existing field
                "bot_user_id": installation.bot_user_id,
                "bot_id": installation.bot_id,
                "enterprise_id": installation.enterprise_id,
                "is_enterprise_install": installation.is_enterprise_install,
                "bot_scopes": installation.bot_scopes,
            }

            # Get team instance from team_id
            from apps.teams.models import Team  # Import here to avoid circular imports

            team = Team.objects.get(id=team_id)

            # Update or create the workspace entry
            SlackWorkspace.objects.update_or_create(
                team=team,
                slack_team_id=installation.team_id,
                defaults=workspace_data,
            )

            self.logger.info(f"Saved installation for Slack team {installation.team_id}, internal team ID: {team_id}")
        except Exception as e:
            self.logger.error(f"Error saving installation: {e}")

    def find_bot(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Bot]:
        """Find a bot installation"""
        try:
            query = SlackWorkspace.objects.all()

            if is_enterprise_install and enterprise_id:
                # For enterprise installs, filter by enterprise ID
                workspace = query.filter(enterprise_id=enterprise_id, is_enterprise_install=True).first()
            else:
                # For workspace installs, filter by team ID
                workspace = query.filter(slack_team_id=team_id).first()

            if not workspace:
                return None

            return Bot(
                app_id=None,  # TODO: add to model
                enterprise_id=workspace.enterprise_id,
                team_id=workspace.slack_team_id,
                bot_token=workspace.access_token,  # Map from your field
                bot_id=workspace.bot_id,
                bot_user_id=workspace.bot_user_id,
                bot_scopes=workspace.bot_scopes,
                installed_at=workspace.installed_at,
            )
        except Exception as e:
            self.logger.error(f"Error finding bot: {e}")
            return None

    def find_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str], 
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Installation]:
        """Find an installation"""
        try:
            query = SlackWorkspace.objects.all()
            if is_enterprise_install and enterprise_id:
                # for enterprise installs, filter by enterprise ID
                workspace = query.filter(enterprise_id=enterprise_id, is_enterprise_install=True).first()
            else:
                # for workspace installs, filter by team ID
                workspace = query.filter(slack_team_id=team_id).first()

            if not workspace:
                return None

            installation = Installation(
                app_id=None,  # TODO: add to model
                enterprise_id=workspace.enterprise_id,
                team_id=workspace.slack_team_id,
                team_name=workspace.slack_team_name,
                bot_token=workspace.access_token,
                bot_id=workspace.bot_id,
                bot_user_id=workspace.bot_user_id,
                bot_scopes=workspace.bot_scopes,
                user_id=None,  # TODO: add to model
                user_token=None,  # TODO: add to model
                user_scopes=None,  # TODO: add to model
                installed_at=workspace.installed_at,
                is_enterprise_install=workspace.is_enterprise_install,
            )

            installation.set_custom_value("team_id", str(workspace.team_id))

            return installation
        except Exception as e:
            self.logger.error(f"Error finding installation: {e}")
            return None

    def delete_bot(self, enterprise_id: Optional[str], team_id: Optional[str]) -> None:
        """Delete a bot installation"""
        query = SlackWorkspace.objects.all()

        if enterprise_id:
            query = query.filter(enterprise_id=enterprise_id)
        if team_id:
            query = query.filter(slack_team_id=team_id)

        query.delete()
        self.logger.info(f"Deleted bot for team {team_id}")

    def delete_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
    ) -> None:
        """Delete an installation"""
        self.delete_bot(enterprise_id=enterprise_id, team_id=team_id)
