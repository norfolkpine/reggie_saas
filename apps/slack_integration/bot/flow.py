from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_bolt.oauth import OAuthFlow
from slack_bolt.request import BoltRequest
from slack_sdk.oauth.installation_store.models import Installation

class CustomOauthFlow(OAuthFlow):
    def store_installation(self, request: BoltRequest, installation: Installation):
        installation.set_custom_value("team", request.context.get("team"))
        super().store_installation(request, installation)

    def issue_new_state(self, request: BoltRequest) -> str:
        return self.settings.state_store.issue(request.context.get("team"))
