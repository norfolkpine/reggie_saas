import json
import requests
from os import getenv
from typing import Any, List, Optional, Dict
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

class GmailTools(Toolkit):
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "google-mail",
        nango_host: Optional[str] = None,
        nango_secret_key: Optional[str] = None,
        nango_connection: Optional[object] = None,
        **kwargs,
    ):
        self.connection_id = connection_id or getenv("GMAIL_CONNECTION_ID")
        self.provider_config_key = provider_config_key
        self.nango_host = nango_host or getattr(settings, 'NANGO_HOST', 'https://nango.opie.sh')
        self.nango_secret_key = nango_secret_key or getattr(settings, 'NANGO_SECRET_KEY', None)
        self.nango_connection = nango_connection

        if not self.connection_id:
            raise ValueError("GMAIL connection_id not provided. Please configure Nango integration first.")
        if not self.nango_secret_key:
            raise ValueError("NANGO_SECRET_KEY not configured.")

        super().__init__(name="gmail_tools", **kwargs)

        # Register methods as Agno tools
        self.register(self.list_messages)
        self.register(self.get_message)
        self.register(self.send_message)
        self.register(self.list_labels)

    def _make_nango_request(self, method: str, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None) -> dict:

        url = f"{self.nango_host}/proxy/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.nango_secret_key}",
            "Connection-Id": self.connection_id,
            "Provider-Config-Key": self.provider_config_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
            if response.status_code == 204 or not response.text.strip():
                return {}
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Nango proxy request failed: {e}")
            raise

    def list_messages(self, query: str = "", max_results: int = 10) -> str:

        try:
            params = {
                "q": query,
                "maxResults": max_results
            }
            endpoint = "gmail/v1/users/me/messages"
            data = self._make_nango_request("GET", endpoint, params=params)
            messages = data.get("messages", [])
            # Optionally fetch message details for each message
            detailed_messages = []
            for msg in messages:
                print("msg:\n", msg)
                msg_id = msg.get("id")
                if msg_id:
                    detailed = self.get_message(msg_id, as_dict=True)
                    if detailed:
                        detailed_messages.append(detailed)
            return json.dumps(detailed_messages)
        except Exception as e:
            logger.error(f"Error listing Gmail messages: {e}")
            return json.dumps([])

    def get_message(self, message_id: str, as_dict: bool = False) -> Any:
   
        try:
            endpoint = f"gmail/v1/users/me/messages/{message_id}"
            data = self._make_nango_request("GET", endpoint, params={"format": "minimal"})
            # Parse headers for useful info
            headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
            snippet = data.get("snippet", "")
            body = ""
            # Try to extract plain text body
            payload = data.get("payload", {})
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        body = part.get("body", {}).get("data", "")
                        break
            elif payload.get("body", {}).get("data"):
                body = payload["body"]["data"]
            # Gmail API returns base64url encoded body
            import base64
            try:
                body = base64.urlsafe_b64decode(body.encode()).decode() if body else ""
            except Exception:
                pass
            msg = {
                "id": data.get("id"),
                "threadId": data.get("threadId"),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": snippet,
                "body": body,
                "labelIds": data.get("labelIds", []),
            }
            return msg if as_dict else json.dumps(msg)
        except Exception as e:
            logger.error(f"Error getting Gmail message {message_id}: {e}")
            return {} if as_dict else json.dumps({})

    def send_message(self, to: str, subject: str, body: str) -> str:

        try:
            import base64
            from email.mime.text import MIMEText
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            endpoint = "gmail/v1/users/me/messages/send"
            data = {"raw": raw}
            sent = self._make_nango_request("POST", endpoint, data=data)
            return json.dumps({
                "status": "success",
                "id": sent.get("id"),
                "threadId": sent.get("threadId"),
                "labelIds": sent.get("labelIds", []),
            })
        except Exception as e:
            logger.error(f"Error sending Gmail message: {e}")
            return json.dumps({"status": "error", "error": str(e)})

    def list_labels(self) -> str:

        try:
            endpoint = "gmail/v1/users/me/labels"
            data = self._make_nango_request("GET", endpoint)
            labels = data.get("labels", [])
            return json.dumps(labels)
        except Exception as e:
            logger.error(f"Error listing Gmail labels: {e}")
            return json.dumps([])

    def _format_emails(self, emails: List[dict]) -> str:
        if not emails:
            return "No emails found"
        formatted_emails = []
        for email in emails:
            formatted_email = (
                f"From: {email.get('from')}\n"
                f"To: {email.get('to')}\n"
                f"Subject: {email.get('subject')}\n"
                f"Date: {email.get('date')}\n"
                f"Body: {email.get('body')}\n"
                f"Message ID: {email.get('id')}\n"
                f"Thread ID: {email.get('threadId')}\n"
                "----------------------------------------"
            )
            formatted_emails.append(formatted_email)
        return "\n\n".join(formatted_emails)