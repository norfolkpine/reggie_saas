import json
import os
from typing import Any, Dict, List, Optional

from agno.tools.toolkit import Toolkit
from agno.utils.log import logger

try:
    from twilio.rest import Client
except ImportError:
    raise ImportError("WhatsApp tools require the `twilio` package. Run `pip install twilio` to install it.")


class WhatsAppTools(Toolkit):
    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        phone_number: Optional[str] = None,
        send_message: bool = True,
        get_messages: bool = True,
        get_account_status: bool = True,
    ):
        super().__init__(name="whatsapp")
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = phone_number or os.getenv("TWILIO_WHATSAPP_NUMBER")

        if not all([self.account_sid, self.auth_token, self.phone_number]):
            raise ValueError("Twilio credentials are not properly configured")

        self.client = Client(self.account_sid, self.auth_token)

        if send_message:
            self.register(self.send_message)
        if get_messages:
            self.register(self.get_messages)
        if get_account_status:
            self.register(self.get_account_status)

    def send_message(self, to: str, message: str) -> str:
        """
        Send a WhatsApp message to a phone number.

        Args:
            to (str): The recipient's phone number in E.164 format (e.g., +1234567890)
            message (str): The message to send

        Returns:
            str: A JSON string containing the response from the Twilio API
        """
        try:
            message = self.client.messages.create(
                from_=f"whatsapp:{self.phone_number}",
                body=message,
                to=f"whatsapp:{to}"
            )
            return json.dumps({
                "status": "success",
                "message_sid": message.sid,
                "status": message.status
            })
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return json.dumps({"error": str(e)})

    def get_messages(self, limit: int = 20) -> str:
        """
        Get recent WhatsApp messages.

        Args:
            limit (int): Maximum number of messages to retrieve (default: 20)

        Returns:
            str: A JSON string containing the list of messages
        """
        try:
            messages = self.client.messages.list(
                from_=f"whatsapp:{self.phone_number}",
                limit=limit
            )
            message_list = [{
                "sid": msg.sid,
                "from": msg.from_,
                "to": msg.to,
                "body": msg.body,
                "status": msg.status,
                "date_sent": str(msg.date_sent)
            } for msg in messages]
            return json.dumps(message_list)
        except Exception as e:
            logger.error(f"Error getting WhatsApp messages: {e}")
            return json.dumps({"error": str(e)})

    def get_account_status(self) -> str:
        """
        Get the status of the WhatsApp account.

        Returns:
            str: A JSON string containing the account status
        """
        try:
            account = self.client.api.accounts(self.account_sid).fetch()
            return json.dumps({
                "status": "success",
                "account_sid": account.sid,
                "status": account.status,
                "type": account.type,
                "friendly_name": account.friendly_name
            })
        except Exception as e:
            logger.error(f"Error getting WhatsApp account status: {e}")
            return json.dumps({"error": str(e)})