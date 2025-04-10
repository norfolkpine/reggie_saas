# slack_integration/bot/factory.py
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from django.conf import settings
from slack_bolt import App
from slack_bolt.adapter.django import SlackRequestHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings

from apps.reggie.agents.tools.custom_slack import SlackTools
from apps.slack_integration.bot.flow import CustomOauthFlow
from apps.slack_integration.storage import DjangoInstallationStore
from slack_sdk.oauth.state_store import FileOAuthStateStore



def build_bolt_app():
    installation_store = DjangoInstallationStore()
    state_store = FileOAuthStateStore(expiration_seconds=600) # TODO: use agno

    oauth_flow = CustomOauthFlow(
        OAuthSettings(
            client_id=settings.SLACK_CLIENT_ID,
            client_secret=settings.SLACK_CLIENT_SECRET,
            scopes=["app_mentions:read", "chat:write"],
            installation_store=installation_store,
            state_store=state_store,
            redirect_uri=settings.SLACK_REDIRECT_URI
        )
    )

    app = App(
        token=settings.SLACK_BOT_TOKEN, 
        signing_secret=settings.SLACK_SIGNING_SECRET,
        installation_store=installation_store,
        oauth_flow=oauth_flow,
    )

    agent = Agent(
        name="Reggie",
        model=OpenAIChat(id="gpt-4o"),
        #model=Gemini(id="gemini-1.5-flash"),
        tools=[SlackTools(
            token=settings.SLACK_BOT_TOKEN,
        )],
        show_tool_calls=True,
        instructions= [
            "If translating, return only the translated text. Use Slack tools.",
            "If replying as reggie on slack, use Slack tools. ALWAYS read context from read_slack_event_context before doing anything, all function for the slack tool is available on the event context. ALWAYS try to get_chat_thread_history, then use tools accordingly. FINALLY, always send_message back, passing mention_user_id obtained from read_slack_event_context data.",
            "Format using currency symbols",
            "Use tools for getting data such as the price of bitcoin"
        ],
        read_chat_history=True,
        add_history_to_messages=True,
        num_history_responses=10,
        markdown=True
    )

    @app.event("app_mention")
    def handle(event, say):
        try:
            if "bot_id" in event or event.get("user") == settings.SLACK_BOT_USER_ID:
                return

            app.client.reactions_add(
                name="alien",
                channel=event["channel"],
                timestamp=event["ts"]
            )

            message_text = event['text']
            if '<@' in message_text:
                message_text = message_text.split('>', 1)[1].strip()

            thread_ts = event.get('thread_ts') or event['ts']

            response: RunResponse = agent.run(
                message=str({
                    "from_user": event['user'],
                    "type": "slack",
                    "message": message_text,
                    "channel": event['channel'],
                    "thread_ts": thread_ts,
                })
            )

            say(response.content.strip(), thread_ts=thread_ts)
            print(f"Response: {response.content.strip()}")

        except Exception as e:
            say(f"⚠️ Sorry, I encountered an error: {str(e)}")

    return SlackRequestHandler(app)