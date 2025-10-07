# slack_integration/bot/factory.py
from agno.agent import Agent
from agno.run.agent import RunOutput
from agno.models.openai import OpenAIChat
from django.conf import settings
from slack_bolt import App
from slack_bolt.adapter.django import SlackRequestHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings

from apps.opie.agents.tools.custom_slack import SlackTools
from apps.opie.utils.token_usage import create_token_usage_record
from apps.slack_integration.bot.flow import CustomOauthFlow
from apps.slack_integration.oauth_storage import DjangoOAuthStateStore
from apps.slack_integration.storage import DjangoInstallationStore


def build_bolt_app():
    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise RuntimeError("Missing Slack OAuth credentials (set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET)")

    installation_store = DjangoInstallationStore(
        client_id=settings.SLACK_CLIENT_ID,
    )
    # state_store = FileOAuthStateStore(expiration_seconds=600)
    state_store = DjangoOAuthStateStore(
        expiration_seconds=120,
    )

    oauth_flow = CustomOauthFlow(
        OAuthSettings(
            client_id=settings.SLACK_CLIENT_ID,
            client_secret=settings.SLACK_CLIENT_SECRET,
            scopes=settings.SLACK_SCOPES,
            installation_store=installation_store,
            state_store=state_store,
            redirect_uri=settings.SLACK_REDIRECT_URI,
            redirect_uri_path="/slack/oauth/callback/",
            install_path="/slack/oauth/start/",
        )
    )

    app = App(
        signing_secret=settings.SLACK_SIGNING_SECRET,
        installation_store=installation_store,
        oauth_flow=oauth_flow,
        # temporary settings for testing
        # token=settings.SLACK_BOT_TOKEN,
        # signing_secret=settings.SLACK_SIGNING_SECRET,
        # token_verification_enabled=False,
    )

    # This will need to be replaced to call an agent from opie AgentBuilder
    agent = Agent(
        name="Opie",
        model=OpenAIChat(id="gpt-4o"),
        # model=Gemini(id="gemini-1.5-flash"),
        tools=[
            SlackTools(
                app=app,
            )
        ],
        instructions=[
            "If translating, return only the translated text. Use Slack tools.",
            "If replying as opie on slack, use Slack tools. ALWAYS read context from read_slack_event_context before doing anything, all function for the slack tool is available on the event context. ALWAYS try to get_chat_thread_history, then use tools accordingly. FINALLY, always send_message back, passing mention_user_id obtained from read_slack_event_context data.",
            "Format using currency symbols",
            "Use tools for getting data such as the price of bitcoin",
        ],
        read_chat_history=True,
        add_history_to_context=True,
        num_history_runs=10,
        markdown=True,
    )

    @app.event("app_mention")
    def handle(event, say):
        try:
            auth_info = app.client.auth_test()
            BOT_USER_ID = auth_info["user_id"]

            if "bot_id" in event or event.get("user") == BOT_USER_ID:
                return

            app.client.reactions_add(name="alien", channel=event["channel"], timestamp=event["ts"])

            message_text = event["text"]
            if "<@" in message_text:
                message_text = message_text.split(">", 1)[1].strip()

            thread_ts = event.get("thread_ts") or event["ts"]
            print(f"Thread timestamp: {thread_ts}")
            print(f"Message text: {message_text}")
            response: RunOutput = agent.run(
                message=str(
                    {
                        "from_user": event["user"],
                        "type": "slack",
                        "message": message_text,
                        "channel": event["channel"],
                        "thread_ts": thread_ts,
                    }
                )
            )

            if hasattr(response, "metrics"):
                metrics = response.metrics.to_dict()
                team = None
                try:
                    from apps.slack_integration.models import SlackWorkspace
                    workspace = SlackWorkspace.objects.get(slack_team_id=event["team_id"])
                    team = workspace.team
                except SlackWorkspace.DoesNotExist:
                    pass
                create_token_usage_record(
                    user=None,
                    session_id=thread_ts,
                    agent_name=agent.name,
                    model_provider="openai",
                    model_name=agent.model.id,
                    input_tokens=metrics.get("input_tokens", 0),
                    output_tokens=metrics.get("output_tokens", 0),
                    total_tokens=metrics.get("total_tokens", 0),
                )

            # say(response.content.strip(), thread_ts=thread_ts)
            print(f"Response: {response.content.strip()}")

        except Exception as e:
            # say(f"⚠️ Sorry, I encountered an error: {str(e)}")
            print(f"⚠️ Sorry, I encountered an error: {str(e)}")

    return SlackRequestHandler(app=app)
