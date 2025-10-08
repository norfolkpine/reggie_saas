import os
import requests
from agno.tools import Toolkit
from agno.utils.log import logger

class JulesApiTools(Toolkit):
    """
    A toolkit for interacting with the Jules API to perform code-related tasks.
    """
    def __init__(self):
        super().__init__(name="jules_api_tools")
        self.base_url = "https://jules.googleapis.com/v1alpha"

        # Retrieve the API key from environment variables
        self.api_key = os.getenv("JULES_API_KEY")
        if not self.api_key:
            logger.warning("JULES_API_KEY environment variable not set. Jules API tool will not work.")
            # You might want to handle this more gracefully,
            # maybe by disabling the tool if the key is not present.

        # Set up the headers for authentication
        self.headers = {
            "X-Goog-Api-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "OpieAgent/1.0"
        }

        # Register the tool's methods
        self.register(self.list_jules_sources)
        self.register(self.start_jules_session)
        self.register(self.get_jules_session_activity)
        self.register(self.send_jules_message)

    def list_jules_sources(self) -> str:
        """
        Lists all available code sources (e.g., GitHub repositories) that Jules can work with.
        """
        if not self.api_key:
            return "Error: JULES_API_KEY is not configured."

        url = f"{self.base_url}/sources"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing Jules sources: {e}")
            return f"Error listing Jules sources: {e}"

    def start_jules_session(self, source: str, prompt: str, title: str = "Jules API Session") -> str:
        """
        Starts a new coding session with Jules on a specific code source.

        Args:
            source (str): The name of the source to work with (e.g., 'sources/github/owner/repo').
            prompt (str): The initial instruction or task for the Jules agent.
            title (str): A descriptive title for the session.

        Returns:
            str: The ID of the newly created session, or an error message.
        """
        if not self.api_key:
            return "Error: JULES_API_KEY is not configured."

        url = f"{self.base_url}/sessions"
        payload = {
            "sourceContext": {"source": source},
            "prompt": prompt,
            "title": title,
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            session_data = response.json()
            return f"Jules session started successfully. Session ID: {session_data.get('id')}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Error starting Jules session: {e}")
            return f"Error starting Jules session: {e}"

    def get_jules_session_activity(self, session_id: str) -> str:
        """
        Fetches the activity stream for a given Jules session to see progress and messages.

        Args:
            session_id (str): The ID of the session to get activity for.

        Returns:
            str: A JSON string of the session's activities, or an error message.
        """
        if not self.api_key:
            return "Error: JULES_API_KEY is not configured."

        url = f"{self.base_url}/sessions/{session_id}/activities"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Jules session activity: {e}")
            return f"Error getting Jules session activity: {e}"

    def send_jules_message(self, session_id: str, prompt: str) -> str:
        """
        Sends a follow-up message or instruction to an active Jules session.

        Args:
            session_id (str): The ID of the session to send a message to.
            prompt (str): The message or instruction for the Jules agent.

        Returns:
            str: A confirmation message or an error.
        """
        if not self.api_key:
            return "Error: JULES_API_KEY is not configured."

        url = f"{self.base_url}/sessions/{session_id}:sendMessage"
        payload = {"prompt": prompt}
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return "Message sent to Jules successfully. Check session activity for response."
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message to Jules: {e}")
            return f"Error sending message to Jules: {e}"