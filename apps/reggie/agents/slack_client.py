from slack_sdk import WebClient
from django.conf import settings

# Initialize Slack WebClient
client = WebClient(token=settings.SLACK_BOT_TOKEN)
