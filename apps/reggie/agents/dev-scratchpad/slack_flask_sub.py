import os
from dotenv import load_dotenv
from slack_sdk.web import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.request import SocketModeRequest

from agno.agent import Agent, RunResponse
from agno.tools.slack import SlackTools
from agno.models.openai import OpenAIChat
from agno.utils.pprint import pprint_run_response
from agno.tools.jira import JiraTools

# === Load environment ===
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-...
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # xapp-...
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # xapp-...

# === Slack SDK Setup ===
web_client = WebClient(token=SLACK_BOT_TOKEN)
client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

# === Agent Setup ===
slack_tools = SlackTools()
jira_tools = JiraTools()

agent = Agent(
    name="Reggie",
    model=OpenAIChat(id="gpt-4o"),
    tools=[slack_tools, jira_tools],
    show_tool_calls=True,
    instructions="If translating, return only the translated text."
)

# === Subscription Check (stubbed function) ===
def has_valid_subscription(team_id: str) -> bool:
    # TODO: Replace this stub with actual DB lookup
    # For example: query your database to see if team_id is valid
    VALID_TEAM_IDS = {"T06LP8F3K8V", "T87654321"}  # Example placeholder
    return team_id in VALID_TEAM_IDS

# def has_valid_subscription(slack_team_id: str) -> bool:
#     try:
#         workspace = SlackWorkspace.objects.get(slack_team_id=slack_team_id)
#         team = workspace.team
#         return team.subscriptions.filter(status="active").exists()
#     except SlackWorkspace.DoesNotExist:
#         return False


# === Process Slack Events ===
def process(client: SocketModeClient, req: SocketModeRequest):
    print("📥 Incoming request:", req.type)

    if req.type != "events_api":
        return

    # Extract workspace ID
    team_id = req.payload.get("team_id")
    print(f"🏢 Workspace ID (team_id): {team_id}")

    # Check for valid subscription
    if not has_valid_subscription(team_id):
        print("🚫 Unauthorized workspace.")
        channel = req.payload.get("event", {}).get("channel")
        if channel:
            client.web_client.chat_postMessage(
                channel=channel,
                text="⚠️ This workspace does not have an active subscription."
            )
        return

    # Acknowledge the event
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

    # Clean text
    if event_type == "app_mention":
        bot_user_id = req.payload["authorizations"][0]["user_id"]
        mention = f"<@{bot_user_id}>"
        cleaned_text = text.replace(mention, "").strip()
    elif event_type == "message" and channel_type == "im":
        cleaned_text = text.strip()
    else:
        print("ℹ️ Unsupported event type, skipping.")
        return

    # Prepare prompt
    if "/tid" in cleaned_text.lower():
        print("🌐 Translating to Indonesian...")
        text_to_translate = cleaned_text.replace("/tid", "").strip()
        prompt = f"Translate this message to Indonesian: {text_to_translate}"
    else:
        prompt = cleaned_text

    try:
        print("\n🧠 Running agent with prompt:")
        print(prompt)
        print("⏳ Waiting for response...\n")

        # Run the agent
        response: RunResponse = agent.run(prompt)
        response_text = response.content.strip()

        # Pretty-print to console
        pprint_run_response(response, markdown=True)

        # Send reply to Slack with Markdown formatting
        client.web_client.chat_postMessage(
            channel=channel,
            text=response_text
        )

    except Exception as e:
        print(f"❌ Error while processing prompt: {e}")
        client.web_client.chat_postMessage(
            channel=channel,
            text="⚠️ Sorry, something went wrong while processing your request."
        )

# === Register and Connect ===
client.socket_mode_request_listeners.append(process)
print("🚀 Connecting to Slack via Socket Mode...")
client.connect()

# === Keep alive ===
from threading import Event
Event().wait()
