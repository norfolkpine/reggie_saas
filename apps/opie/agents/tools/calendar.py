import json
import requests
from os import getenv
from typing import Any, List, Optional, Dict
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

class GoogleCalendarTools(Toolkit):
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "google-calendar",
        nango_host: Optional[str] = None,
        nango_secret_key: Optional[str] = None,
        nango_connection: Optional[object] = None,
        **kwargs,
    ):
        self.connection_id = connection_id or getenv("GOOGLE_CALENDAR_CONNECTION_ID")
        self.provider_config_key = provider_config_key
        self.nango_host = nango_host or getattr(settings, 'NANGO_HOST', 'https://nango.opie.sh')
        self.nango_secret_key = nango_secret_key or getattr(settings, 'NANGO_SECRET_KEY', None)
        self.nango_connection = nango_connection

        if not self.connection_id:
            raise ValueError("Google Calendar connection_id not provided. Please configure Nango integration first.")
        if not self.nango_secret_key:
            raise ValueError("NANGO_SECRET_KEY not configured.")

        super().__init__(name="google_calendar_tools", **kwargs)

        # Register methods as Agno tools
        self.register(self.list_calendars)
        self.register(self.list_events)
        self.register(self.get_event)
        self.register(self.create_event)
        self.register(self.update_event)
        self.register(self.delete_event)

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
            elif method.upper() == "PUT" or method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, json=data, params=params)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
            if response.status_code == 204 or not response.text.strip():
                return {}
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Nango proxy request failed: {e}")
            raise

    def list_calendars(self) -> str:
        """List all calendars for the user."""
        try:
            endpoint = "calendar/v3/users/me/calendarList"
            data = self._make_nango_request("GET", endpoint)
            calendars = data.get("items", [])
            return json.dumps(calendars)
        except Exception as e:
            logger.error(f"Error listing Google calendars: {e}")
            return json.dumps([])

    def list_events(self, calendar_id: str = "primary", max_results: int = 10) -> str:
        """List upcoming events on a calendar."""
        try:
            endpoint = f"calendar/v3/calendars/{calendar_id}/events"
            params = {"maxResults": max_results, "singleEvents": True, "orderBy": "startTime"}
            data = self._make_nango_request("GET", endpoint, params=params)
            events = data.get("items", [])
            return json.dumps(events)
        except Exception as e:
            logger.error(f"Error listing Google calendar events: {e}")
            return json.dumps([])

    def get_event(self, calendar_id: str, event_id: str) -> str:
        """Get details for a specific event."""
        try:
            endpoint = f"calendar/v3/calendars/{calendar_id}/events/{event_id}"
            data = self._make_nango_request("GET", endpoint)
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error getting Google calendar event: {e}")
            return json.dumps({})

    def create_event(self, calendar_id: str, summary: str, start_time: str, end_time: str, description: str = "", location: str = "", attendees: Optional[List[str]] = None) -> str:
        """
        Create a new event.
        start_time and end_time should be RFC3339 timestamp strings (e.g. "2024-06-01T10:00:00-07:00")
        """
        try:
            endpoint = f"calendar/v3/calendars/{calendar_id}/events"
            event = {
                "summary": summary,
                "description": description,
                "location": location,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }
            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]
            data = self._make_nango_request("POST", endpoint, data=event)
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error creating Google calendar event: {e}")
            return json.dumps({"error": str(e)})

    def update_event(self, calendar_id: str, event_id: str, updates: Dict[str, Any]) -> str:
        """Update an event. `updates` is a dict of fields to update."""
        try:
            endpoint = f"calendar/v3/calendars/{calendar_id}/events/{event_id}"
            data = self._make_nango_request("PATCH", endpoint, data=updates)
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error updating Google calendar event: {e}")
            return json.dumps({"error": str(e)})

    def delete_event(self, calendar_id: str, event_id: str) -> str:
        """Delete an event."""
        try:
            endpoint = f"calendar/v3/calendars/{calendar_id}/events/{event_id}"
            self._make_nango_request("DELETE", endpoint)
            return json.dumps({"status": "deleted"})
        except Exception as e:
            logger.error(f"Error deleting Google calendar event: {e}")
            return json.dumps({"error": str(e)})