# slack_integration/bot/factory.py
from slack_integration.storage import DjangoInstallationStore


def build_bolt_app():
    installation_store = DjangoInstallationStore()
    state_store = FileStateStore(expiration_seconds=600)

    oauth_flow = CustomOauthFlow(
        OAuthSettings(
            client_id=os.getenv("SLACK_CLIENT_ID"),
            client_secret=os.getenv("SLACK_CLIENT_SECRET"),
            scopes=["app_mentions:read", "chat:write"],
            installation_store=installation_store,
            state_store=state_store,
        )
    )

    app = App(oauth_flow=oauth_flow)

    @app.event("app_mention")
    def handle_mention(event, say):
        say("Hey there! 👋")

    return SlackRequestHandler(app)
