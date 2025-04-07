import os

from slack_bolt import App
from slack_bolt.adapter.django import SlackRequestHandler
from slack_bolt.oauth.installation_store.sqlalchemy import SQLAlchemyInstallationStore
from slack_bolt.oauth.state_store import FileStateStore

from .flow import CustomOauthFlow


def build_bolt_app():
    installation_store = SQLAlchemyInstallationStore(
        client_id=os.getenv("SLACK_CLIENT_ID"),
        client_secret=os.getenv("SLACK_CLIENT_SECRET"),
        database=os.getenv("DATABASE_URL"),  # Uses production DB configured in settings.py
    )
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
