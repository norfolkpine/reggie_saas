import os

from dotenv import load_dotenv
from slack_sdk import WebClient

# Load environment variables from .env file
load_dotenv()

# Get token from environment
slack_token = os.getenv("SLACK_TOKEN")

# Initialize Slack WebClient
client = WebClient(token=slack_token)


import os

from agno.agent import Agent
from agno.tools.slack import SlackTools

slack_tools = SlackTools()

agent = Agent(tools=[slack_tools], show_tool_calls=True)

# Example 1: Send a message to a Slack channel
# agent.print_response("Send a message 'Hello, I'm Reggie!' to the channel #general", markdown=True)

# Example 2: List all channels in the Slack workspace
# agent.print_response("List all channels in our Slack workspace", markdown=True)

# Example 3: Get the message history of a specific channel by channel ID
# agent.print_response("Get the last 10 messages from the channel C0816V1KNEP", markdown=True)

# Example 3: Get the message history of a specific channel by channel ID
agent.print_response("Get me a list of links from the channel C0816V1KNEP", markdown=True)
