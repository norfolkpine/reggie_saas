import os
import requests
from threading import Event
from dotenv import load_dotenv
from slack_sdk.web import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from agno.tools.slack import SlackTools
from agno.tools.jira import JiraTools

# === Load environment variables ===
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

# === Setup Slack clients ===
web_client = WebClient(token=SLACK_BOT_TOKEN)
client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

# Fetch bot metadata
auth_info = web_client.auth_test()
BOT_USER_ID = auth_info["user_id"]
TEAM_ID = auth_info["team_id"]

# === Setup AI Agent ===
agent = Agent(
    name="Reggie",
    model=OpenAIChat(id="gpt-4o"),
    tools=[SlackTools(), JiraTools()],
    show_tool_calls=True,
    instructions="If translating, return only the translated text. Use Slack tools."
)

# === Check for subscription (stubbed) ===
def has_valid_subscription(team_id: str) -> bool:
    VALID_TEAM_IDS = {"T06LP8F3K8V", "T87654321"}
    return team_id in VALID_TEAM_IDS

# Future code for tracking against SaaS service
# def has_valid_subscription(slack_team_id: str) -> bool:
#     try:
#         workspace = SlackWorkspace.objects.get(slack_team_id=slack_team_id)
#         team = workspace.team
#         return team.subscriptions.filter(status="active").exists()
#     except SlackWorkspace.DoesNotExist:
#         return False

# === SocketMode main handler ===
def process(client: SocketModeClient, req: SocketModeRequest):
    print(f"📥 Incoming request: {req.type}")

    # Always acknowledge the event
    try:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    except Exception as e:
        print(f"❗ Failed to ACK Slack request: {e}")
        return

    if not has_valid_subscription(TEAM_ID):
        print("🚫 Unauthorized workspace.")
        channel = req.payload.get("event", {}).get("channel")
        if channel:
            client.web_client.chat_postMessage(
                channel=channel,
                text="⚠️ This workspace does not have an active subscription."
            )
        return

    if req.payload.get("response_url"):
        requests.post(req.payload["response_url"], json={"text": "⚙️ Processing... Please wait."})

    try:
        if req.type == "slash_commands":
            handle_slash_command(req)
        elif req.type == "events_api":
            handle_events_api(req)
        else:
            print(f"ℹ️ Unsupported request type: {req.type}")
    except Exception as e:
        print(f"❌ Error while processing request: {e}")

# === Handle slash commands ===
def handle_slash_command(req: SocketModeRequest):
    command = req.payload.get("command")
    text = req.payload.get("text", "").strip()
    user_id = req.payload.get("user_id")
    response_url = req.payload.get("response_url")

    print(f"📎 Slash command: {command}, Text: {text}")

    translation_prompts = {
        "/indo": f"Translate this message to informal Indonesian: {text}",
        "/en": f"Translate this message to English: {text}"
    }

    prompt = translation_prompts.get(command)
    if not prompt:
        print("⚠️ Unrecognized slash command.")
        return

    try:
        response: RunResponse = agent.run(prompt)
        translation = response.content.strip()
        final_text = f">From: <@{user_id}>\n>{text}\n```{translation}```"

        requests.post(
            response_url,
            json={
                "response_type": "in_channel",  # or "ephemeral" for private response
                "text": final_text
            }
        )

    except Exception as e:
        print(f"❌ Error in slash command handler: {e}")
        requests.post(
            response_url,
            json={"text": "⚠️ Sorry, something went wrong while processing your translation request."}
        )

# === Handle Events API (mentions and DMs) ===
def handle_events_api(req: SocketModeRequest):
    event = req.payload.get("event", {})
    user = event.get("user")
    bot_id = event.get("bot_id")
    if bot_id or user == BOT_USER_ID:
        print("🤖 Ignoring bot message.")
        return

    event_type = event.get("type")
    channel = event.get("channel")
    channel_type = event.get("channel_type")
    text = event.get("text", "").strip()
    thread_ts = event.get("thread_ts") or event.get("ts")

    # React to acknowledge
    try:
        client.web_client.reactions_add(
            name="eyes",
            channel=channel,
            timestamp=event["ts"]
        )
    except Exception as e:
        print(f"⚠️ Failed to react to message: {e}")

    try:
        if event_type == "app_mention":
            bot_user_id = req.payload["authorizations"][0]["user_id"]
            cleaned_text = text.replace(f"<@{bot_user_id}>", "").strip()
            print(f"💬 Mention from <@{user}>: {cleaned_text}")

            response: RunResponse = agent.run(cleaned_text)
            final_text = f">{text}\n<@{user}> {response.content.strip()}"

            client.web_client.chat_postMessage(
                channel=channel,
                text=final_text,
                thread_ts=thread_ts
            )

        elif event_type == "message" and channel_type == "im":
            print(f"📩 DM from <@{user}>: {text}")
            response: RunResponse = agent.run(text)
            client.web_client.chat_postMessage(
                channel=channel,
                text=response.content.strip(),
                thread_ts=thread_ts
            )

        else:
            print("ℹ️ Event type not supported.")

    except Exception as e:
        print(f"❌ Error in event handler: {e}")
        client.web_client.chat_postMessage(
            channel=channel,
            text="⚠️ Sorry, something went wrong while processing your request."
        )

# === Start Socket Mode connection ===
client.socket_mode_request_listeners.append(process)
print("🚀 Connecting to Slack via Socket Mode...")
client.connect()
Event().wait()
