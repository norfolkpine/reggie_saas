from typing import Any, Dict, Optional

from slack_bolt.oauth import OAuthFlow
from slack_bolt.request import BoltRequest
from slack_sdk.oauth.installation_store.models import Installation


class CustomOauthFlow(OAuthFlow):
    def __init__(self, settings):
        super().__init__(settings=settings)

    def store_installation(self, request: BoltRequest, installation: Installation):
        """
        Store installation with team_id from OAuth state
        """
        # Get team_id from the request context if available
        team_id = request.context.get("team_id") if hasattr(request, "context") else None

        if team_id:
            # Set the team_id as a custom value on the installation
            installation.set_custom_value("team_id", team_id)

        # Call the parent implementation to store the installation
        super().store_installation(request, installation)

    def issue_new_state(self, request: BoltRequest) -> str:
        """
        Issue a new OAuth state and include the team_id
        """
        # Extract team_id from request params
        team_id = request.query.get("team_id", None)

        if team_id:
            # Store team_id with the state
            return self.settings.state_store.issue(team_id=team_id)

        # Default behavior
        return self.settings.state_store.issue()

    def handle_callback(self, request: BoltRequest) -> Optional[Dict[str, Any]]:
        """
        Override to extract team_id from the state and add it to the context
        """
        # Get state from the request
        state = request.query.get("state", None)

        if state:
            # Consume the state and get the team_id
            state_data = self.settings.state_store.consume(state)

            # If we have team_id in the state data, add it to the request context
            if state_data and "team_id" in state_data:
                if not hasattr(request, "context"):
                    request.context = {}
                request.context["team_id"] = state_data["team_id"]

        # Call the parent implementation
        return super().handle_callback(request)
