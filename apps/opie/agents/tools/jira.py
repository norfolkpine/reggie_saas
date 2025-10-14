import json
import requests
from os import getenv
from typing import Any, List, Optional, cast
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger


class JiraTools(Toolkit):
    """
    Jira integration tools using Nango proxy for authentication and API access.
    
    This toolkit provides methods to interact with Jira through Nango's proxy API,
    eliminating the need for direct Jira authentication credentials.
    
    Usage:
        # Initialize with connection_id from Nango integration
        jira_tools = JiraTools(connection_id="your_nango_connection_id")
        
        # Or use environment variable
        # Set JIRA_CONNECTION_ID environment variable
        jira_tools = JiraTools()
        
        # Use the tools
        result = jira_tools.get_issue("PROJ-123")
        result = jira_tools.create_issue("PROJ", "Summary", "Description")
        result = jira_tools.search_issues("project = PROJ")
        result = jira_tools.add_comment("PROJ-123", "Comment text")
    """
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "jira",
        nango_host: Optional[str] = None,
        nango_secret_key: Optional[str] = None,
        **kwargs,
    ):
        self.connection_id = connection_id or getenv("JIRA_CONNECTION_ID")
        self.provider_config_key = provider_config_key
        self.nango_host = nango_host or getattr(settings, 'NANGO_HOST', 'https://nango.opie.sh')
        self.nango_secret_key = nango_secret_key or getattr(settings, 'NANGO_SECRET_KEY', None)

        if not self.connection_id:
            raise ValueError("JIRA connection_id not provided. Please configure Nango integration first.")
        
        if not self.nango_secret_key:
            raise ValueError("NANGO_SECRET_KEY not configured.")

        super().__init__(name="jira_tools", **kwargs)
        
        # Register the methods as Agno tools (exactly like CoinGeckoTools)
        self.register(self.get_issue)
        self.register(self.create_issue)
        self.register(self.search_issues)
        self.register(self.add_comment)
        self.register(self.get_boards)
        self.register(self.get_board)
        self.register(self.get_board_issues)

    def _make_nango_request(self, method: str, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        """
        Make a request to Jira via Nango proxy.
        
        :param method: HTTP method (GET, POST, PUT, etc.)
        :param endpoint: Jira API endpoint (without base URL)
        :param data: Request body data for POST/PUT requests
        :param params: Query parameters
        :return: Response data as dictionary
        """
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
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Nango proxy request failed: {e}")
            raise

    def get_issue(self, issue_key: str) -> str:
        """
        Retrieves issue details from Jira via Nango proxy.

        :param issue_key: The key of the issue to retrieve.
        :return: A JSON string containing issue details.
        """
        # Fake data for testing
        issue_details = {
            "key": issue_key,
            "project": "TEST",
            "issuetype": "Task",
            "reporter": "Test User",
            "summary": f"Test issue {issue_key}",
            "description": "This is a test issue for demonstration purposes",
            "status": "Open",
            "assignee": "Unassigned"
        }
        log_debug(f"Fake issue details retrieved for {issue_key}: {issue_details}")
        return json.dumps(issue_details)

    def create_issue(self, project_key: str, summary: str, description: str, issuetype: str = "Task") -> str:
        """
        Creates a new issue in Jira via Nango proxy.

        :param project_key: The key of the project in which to create the issue.
        :param summary: The summary of the issue.
        :param description: The description of the issue.
        :param issuetype: The type of issue to create.
        :return: A JSON string with the new issue's key and URL.
        """
        # Fake data for testing
        fake_key = f"{project_key}-{hash(summary) % 1000}"
        fake_url = f"https://fake-jira.com/browse/{fake_key}"

        real_url = f"https://benheath.atlassian.net/"
        
        result = {"key": fake_key, "url": fake_url}
        log_debug(f"Fake issue created: {result}")
        return json.dumps(result)

    def search_issues(self, jql_str: str, max_results: int = 50) -> str:
        """
        Searches for issues using a JQL query via Nango proxy.

        :param jql_str: The JQL query string.
        :param max_results: Maximum number of results to return.
        :return: A JSON string containing a list of dictionaries with issue details.
        """
        # Fake data for testing
        fake_issues = [
            {"key": "TEST-1", "summary": "Test issue 1", "status": "Open", "assignee": "Unassigned"},
            {"key": "TEST-2", "summary": "Test issue 2", "status": "In Progress", "assignee": "Test User"},
            {"key": "TEST-3", "summary": "Test issue 3", "status": "Done", "assignee": "Test User"}
        ]
        
        log_debug(f"Fake search results for JQL '{jql_str}': {len(fake_issues)} issues")
        return json.dumps(fake_issues)

    def add_comment(self, issue_key: str, comment: str) -> str:
        """
        Adds a comment to an issue via Nango proxy.

        :param issue_key: The key of the issue.
        :param comment: The comment text.
        :return: A JSON string indicating success or containing an error message.
        """
        # Fake success for testing
        result = {"status": "success", "issue_key": issue_key, "comment": comment}
        log_debug(f"Fake comment added to issue {issue_key}: {comment}")
        return json.dumps(result)

    def get_boards(self, project_key: Optional[str] = None, board_type: Optional[str] = None) -> str:
        """
        Gets all boards or boards for a specific project.

        :param project_key: Optional project key to filter boards
        :param board_type: Optional board type (scrum, kanban, simple)
        :return: A JSON string containing board information
        """
        try:
            params = {}
            if project_key:
                params['projectKeyOrId'] = project_key
            if board_type:
                params['type'] = board_type
                
            response_data = self._make_nango_request("GET", "rest/agile/1.0/board", params=params)
            boards = response_data.get("values", [])
            
            log_debug(f"Retrieved {len(boards)} boards from Jira")
            return json.dumps(boards)
        except Exception as e:
            logger.error(f"Error retrieving boards: {e}")
            return json.dumps({"error": str(e)})

    def get_board(self, board_id: int) -> str:
        """
        Gets a specific board by ID.

        :param board_id: The ID of the board to retrieve
        :return: A JSON string containing board details
        """
        try:
            response_data = self._make_nango_request("GET", f"rest/agile/1.0/board/{board_id}")
            log_debug(f"Retrieved board details for board {board_id}")
            return json.dumps(response_data)
        except Exception as e:
            logger.error(f"Error retrieving board {board_id}: {e}")
            return json.dumps({"error": str(e)})

    def get_board_issues(self, board_id: int, jql: Optional[str] = None, max_results: int = 50) -> str:
        """
        Gets issues for a specific board.

        :param board_id: The ID of the board
        :param jql: Optional JQL query to filter issues
        :param max_results: Maximum number of results to return
        :return: A JSON string containing board issues
        """
        try:
            params = {
                'maxResults': max_results
            }
            if jql:
                params['jql'] = jql
                
            response_data = self._make_nango_request("GET", f"rest/agile/1.0/board/{board_id}/issue", params=params)
            issues = response_data.get("issues", [])
            
            log_debug(f"Retrieved {len(issues)} issues for board {board_id}")
            return json.dumps(issues)
        except Exception as e:
            logger.error(f"Error retrieving board issues for board {board_id}: {e}")
            return json.dumps({"error": str(e)})
