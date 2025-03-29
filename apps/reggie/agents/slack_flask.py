import os
from dotenv import load_dotenv
from slack_sdk.web import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

from agno.agent import Agent
from agno.tools.slack import SlackTools
from agno.models.openai import OpenAIChat

# === Load environment ===
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-...
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # xapp-...

# === Slack SDK Setup ===
web_client = WebClient(token=SLACK_BOT_TOKEN)
client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

# === Agno Agent Setup ===
slack_tools = SlackTools()
agent = Agent(
        name="AgnoAssist",
        model=OpenAIChat(id="gpt-4o"),
        tools=[slack_tools], show_tool_calls=True,
        instructions="If translating, return only the translated text")

# === Process Slack Events ===
def process(client: SocketModeClient, req: SocketModeRequest):
    print("📥 Incoming request:", req.type)

    if req.type == "events_api":
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        event = req.payload.get("event", {})
        event_type = event.get("type")
        channel_type = event.get("channel_type")
        user = event.get("user")
        text = event.get("text")
        channel = event.get("channel")

        if not text or not channel or not user:
            print("⚠️ Incomplete event, skipping.")
            return

        print(f"🔍 Event Type: {event_type} | Channel Type: {channel_type}")
        print(f"👤 User: {user}")
        print(f"💬 Message: {text}")
        print(f"📡 Channel: {channel}")

        # Handle @bot mentions in public channels
        if event_type == "app_mention":
            bot_user_id = req.payload["authorizations"][0]["user_id"]
            mention = f"<@{bot_user_id}>"
            cleaned_text = text.replace(mention, "").strip()

        # Handle DMs
        elif event_type == "message" and channel_type == "im":
            cleaned_text = text.strip()

        else:
            print("ℹ️ Unsupported event type, skipping.")
            return

        # Respond via Agno
        if "/tid" in cleaned_text.lower():
            print("🌐 Translating to Indonesian...")
            text_to_translate = cleaned_text.replace("/tid", "").strip()
            prompt = f"Translate this message to Indonesian: {text_to_translate}"
            #response_text = agent.get_response(prompt)
            response = agent.get_response(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)

        else:
            print("💡 Getting response from Agno...")
            response = agent.get_response(cleaned_text)
            response_text = response.text if hasattr(response, "text") else str(response)


        print(f"📤 Sending response: {response_text}")
        client.web_client.chat_postMessage(channel=channel, text=response_text)

# === Register and Connect ===
client.socket_mode_request_listeners.append(process)
print("🚀 Connecting to Slack via Socket Mode...")
client.connect()

from threading import Event
Event().wait()
