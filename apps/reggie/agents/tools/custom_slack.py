import json
import os
from typing import Any, Dict, List, Optional

from agno.tools.toolkit import Toolkit
from agno.utils.log import logger

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    raise ImportError("Slack tools require the `slack_sdk` package. Run `pip install slack-sdk` to install it.")


class SlackTools(Toolkit):
    def __init__(
        self,
        token: Optional[str] = None,
        send_message: bool = True,
        list_channels: bool = True,
        get_channel_history: bool = True,
        is_thread_valid: bool = True,
        get_thread_history: bool = True,
        get_detailed_channel_information: bool = True
    ):
        super().__init__(name="slack")
        self.token: Optional[str] = token or os.getenv("SLACK_TOKEN")
        if self.token is None or self.token == "":
            raise ValueError("SLACK_TOKEN is not set")
        self.client = WebClient(token=self.token)
        if send_message:
            self.register(self.send_message)
        if list_channels:
            self.register(self.list_channels)
        if get_channel_history:
            self.register(self.get_channel_history)
        if is_thread_valid:
            self.register(self.is_thread_valid)
        if get_thread_history:
            self.register(self.get_thread_history)
        if get_detailed_channel_information:
            self.register(self.get_detailed_channel_information)

    def send_message(self, channel: str, text: str, thread_ts: Optional[str]=None) -> str:
        """
        Send a message to a Slack channel.

        Args:
            channel (str): The channel ID or name to send the message to.
            text (str): The text of the message to send.

        Returns:
            str: A JSON string containing the response from the Slack API.
        """
        try:
            response = self.client.chat_postMessage(channel=channel, text=text, mrkdwn=True, thread_ts=thread_ts)
            return json.dumps(response.data)
        except SlackApiError as e:
            logger.error(f"Error sending message: {e}")
            return json.dumps({"error": str(e)})

    def list_channels(self) -> str:
        """
        List all channels in the Slack workspace.

        Returns:
            str: A JSON string containing the list of channels.
        """
        try:
            response = self.client.conversations_list()
            channels = [{"id": channel["id"], "name": channel["name"]} for channel in response["channels"]]
            return json.dumps(channels)
        except SlackApiError as e:
            logger.error(f"Error listing channels: {e}")
            return json.dumps({"error": str(e)})

    def get_channel_history(self, channel: str, limit: int = 100) -> str:
        """
        Get the message history of a Slack channel.

        Args:
            channel (str): The channel ID to fetch history from.
            limit (int): The maximum number of messages to fetch. Defaults to 100.

        Returns:
            str: A JSON string containing the channel's message history.
        """
        try:
            response = self.client.conversations_history(channel=channel, limit=limit)
            messages: List[Dict[str, Any]] = [  # type: ignore
                {
                    "text": msg.get("text", ""),
                    "user": "webhook" if msg.get("subtype") == "bot_message" else msg.get("user", "unknown"),
                    "ts": msg.get("ts", ""),
                    "sub_type": msg.get("subtype", "unknown"),
                    "attachments": msg.get("attachments", []) if msg.get("subtype") == "bot_message" else "n/a",
                }
                for msg in response.get("messages", [])
            ]
            return json.dumps(messages)
        except SlackApiError as e:
            logger.error(f"Error getting channel history: {e}")
            return json.dumps({"error": str(e)})

    def is_thread_valid(self, channel: str, thread_ts: str) -> str:
        """
        Check if a thread is valid in a channel.

        Args:
            channel (str): The channel ID to check the thread in.
            thread_ts (str): The timestamp of the thread.

        Returns:
            str: A JSON string indicating whether the thread is valid.
        """
        try:
            response = self.client.conversations_replies(channel=channel, ts=thread_ts)
            is_valid = len(response["messages"]) > 1
            return json.dumps({"is_valid": is_valid})
        except SlackApiError as e:
            logger.error(f"Error checking thread validity: {e}")
            return json.dumps({"error": str(e), "is_valid": False})
    
    def get_thread_history(self, channel: str, thread_ts: str, limit: int = 100) -> str:
        """
        Get the message history of a thread in a Slack channel.

        Args:
            channel (str): The channel ID to fetch thread history from.
            thread_ts (str): The timestamp of the thread.

        Returns:
            str: A JSON string containing the thread's message history.
        """
        try:
            response = self.client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                limit=limit
            )
            messages: List[Dict[str, Any]] = [
                {
                    "text": msg.get("text", ""),
                    "user": "webhook" if msg.get("subtype") == "bot_message" else msg.get("user", "unknown"),
                    "ts": msg.get("ts", ""),
                    "sub_type": msg.get("subtype", "unknown"),
                    "attachments": msg.get("attachments", []) if msg.get("subtype") == "bot_message" else "n/a",
                }
                for msg in response.get("messages", [])
            ]
            return json.dumps(messages)
        except SlackApiError as e:
            logger.error(f"Error getting thread history: {e}")
            return json.dumps({"error": str(e)})
    
    def get_detailed_channel_information(self, channelID: str) -> str:
        try:
            response = self.client.conversations_info(channel=channelID)
            return json.dumps(response.data)
        except SlackApiError as e:
            logger.error(f"Error getting channel info: {e}")
            return json.dumps({"error": str(e)})