from slack_bolt.oauth import OAuthFlow
from slack_bolt.request import BoltRequest
from slack_sdk.oauth.installation_store.models import Installation


class CustomOauthFlow(OAuthFlow):
    def __init__(self, settings):
        # Use keyword argument with * to match the parent class signature
        super().__init__(settings=settings)

    def store_installation(self, request: BoltRequest, installation: Installation):
        # Extract team from the context if available
        team = request.context.get("team") if hasattr(request, "context") else None

        if team:
            # Set a custom value that our storage can use
            installation.set_custom_value("team", team)

        super().store_installation(request, installation)

    def issue_new_state(self, request: BoltRequest) -> str:
        # Add team to the state if available
        team = request.context.get("team") if hasattr(request, "context") else None

        if team:
            return self.settings.state_store.issue(team)
        return self.settings.state_store.issue()
