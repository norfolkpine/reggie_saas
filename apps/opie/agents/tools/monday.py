import json
import requests
from os import getenv
from typing import Any, List, Optional, cast
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

class MondayTools(Toolkit):
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "monday",
        nango_host: Optional[str] = None,
        nango_secret_key: Optional[str] = None,
        nango_connection: Optional[object] = None,
        **kwargs,
    ):
        self.connection_id = connection_id
        self.provider_config_key = provider_config_key
        self.nango_host = nango_host or getattr(settings, 'NANGO_HOST', 'https://nango.opie.sh')
        self.nango_secret_key = nango_secret_key or getattr(settings, 'NANGO_SECRET_KEY', None)
        self.nango_connection = nango_connection  # Store the connection object

        if not self.nango_secret_key:
            raise ValueError("NANGO_SECRET_KEY not configured.")

        super().__init__(name="monday_tools", **kwargs)

        # Register the methods as Agno tools (exactly like CoinGeckoTools and JiraTools)
        self.register(self.get_boards)
        self.register(self.get_board)
        self.register(self.create_item)
        self.register(self.get_items)
        self.register(self.update_item)
        self.register(self.get_columns)
        self.register(self.get_users)
        self.register(self.create_update)

    def _make_nango_request(self, method: str, endpoint: str, data: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        """
        Make a request to Monday.com via Nango proxy.

        :param method: HTTP method (GET, POST, PUT, etc.)
        :param endpoint: Monday API endpoint (without base URL)
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

            # Handle empty responses (like 204 No Content)
            if response.status_code == 204 or not response.text.strip():
                return {}

            json_data = response.json()
            return json_data if json_data is not None else {}
        except requests.RequestException as e:
            logger.error(f"Nango proxy request failed: {e}")
            raise

    def get_boards(self, limit: int = 50) -> str:
        """
        Get all boards accessible to the user.

        :param limit: Maximum number of boards to return
        :return: A JSON string containing board information
        """
        try:
            query = f"""
            query {{
                boards (limit: {limit}) {{
                    id
                    name
                    description
                    board_kind
                    state
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            boards = response_data.get("data", {}).get("boards", [])
            log_debug(f"Retrieved {len(boards)} boards from Monday.com")
            return json.dumps(boards)

        except Exception as e:
            logger.error(f"Error retrieving boards: {e}")
            fallback_boards = [
                {
                    "id": "demo-board-1",
                    "name": "Demo Board",
                    "description": "Demo board for testing",
                    "board_kind": "public",
                    "state": "active"
                }
            ]
            return json.dumps(fallback_boards)

    def get_board(self, board_id: str) -> str:
        """
        Get details of a specific board by ID.

        :param board_id: The ID of the board to retrieve
        :return: A JSON string containing board details
        """
        try:
            query = f"""
            query {{
                boards (ids: [{board_id}]) {{
                    id
                    name
                    description
                    board_kind
                    state
                    columns {{
                        id
                        title
                        type
                    }}
                    groups {{
                        id
                        title
                    }}
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            boards = response_data.get("data", {}).get("boards", [])
            if boards:
                board = boards[0]
                log_debug(f"Retrieved board {board_id}: {board.get('name')}")
                return json.dumps(board)
            else:
                raise ValueError(f"Board {board_id} not found")

        except Exception as e:
            logger.error(f"Error retrieving board {board_id}: {e}")
            fallback_board = {
                "id": board_id,
                "name": f"Demo Board {board_id}",
                "description": "Demo board for testing",
                "board_kind": "public",
                "state": "active",
                "columns": [],
                "groups": []
            }
            return json.dumps(fallback_board)

    def create_item(self, board_id: str, item_name: str, group_id: Optional[str] = None, column_values: Optional[dict] = None) -> str:
        """
        Create a new item (task/row) in a Monday.com board.

        :param board_id: The ID of the board
        :param item_name: The name of the item to create
        :param group_id: Optional group ID to place the item in
        :param column_values: Optional dictionary of column values to set
        :return: A JSON string with the created item details
        """
        try:
            # Build column_values JSON string if provided
            column_values_str = ""
            if column_values:
                column_values_json = json.dumps(json.dumps(column_values))
                column_values_str = f', column_values: {column_values_json}'

            # Build group_id parameter if provided
            group_id_str = f', group_id: "{group_id}"' if group_id else ""

            query = f"""
            mutation {{
                create_item (
                    board_id: {board_id},
                    item_name: "{item_name}"{group_id_str}{column_values_str}
                ) {{
                    id
                    name
                    state
                    created_at
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            item = response_data.get("data", {}).get("create_item", {})
            log_debug(f"Created item in board {board_id}: {item_name}")
            return json.dumps({
                "status": "success",
                "item": item
            })

        except Exception as e:
            logger.error(f"Error creating item in board {board_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "board_id": board_id,
                "item_name": item_name
            })

    def get_items(self, board_id: str, limit: int = 50) -> str:
        """
        Get items (tasks/rows) from a specific board.

        :param board_id: The ID of the board
        :param limit: Maximum number of items to return
        :return: A JSON string containing board items
        """
        try:
            query = f"""
            query {{
                boards (ids: [{board_id}]) {{
                    items (limit: {limit}) {{
                        id
                        name
                        state
                        created_at
                        updated_at
                        column_values {{
                            id
                            title
                            text
                            type
                        }}
                        group {{
                            id
                            title
                        }}
                    }}
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            boards = response_data.get("data", {}).get("boards", [])
            if boards:
                items = boards[0].get("items", [])
                log_debug(f"Retrieved {len(items)} items from board {board_id}")
                return json.dumps(items)
            else:
                return json.dumps([])

        except Exception as e:
            logger.error(f"Error retrieving items from board {board_id}: {e}")
            return json.dumps([])

    def update_item(self, item_id: str, board_id: str, column_values: dict) -> str:
        """
        Update column values of an existing item.

        :param item_id: The ID of the item to update
        :param board_id: The ID of the board containing the item
        :param column_values: Dictionary of column values to update
        :return: A JSON string with the update result
        """
        try:
            column_values_json = json.dumps(json.dumps(column_values))

            query = f"""
            mutation {{
                change_multiple_column_values (
                    item_id: {item_id},
                    board_id: {board_id},
                    column_values: {column_values_json}
                ) {{
                    id
                    name
                    updated_at
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            item = response_data.get("data", {}).get("change_multiple_column_values", {})
            log_debug(f"Updated item {item_id} in board {board_id}")
            return json.dumps({
                "status": "success",
                "item": item
            })

        except Exception as e:
            logger.error(f"Error updating item {item_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "item_id": item_id,
                "board_id": board_id
            })

    def get_columns(self, board_id: str) -> str:
        """
        Get all columns from a specific board.

        :param board_id: The ID of the board
        :return: A JSON string containing column information
        """
        try:
            query = f"""
            query {{
                boards (ids: [{board_id}]) {{
                    columns {{
                        id
                        title
                        type
                        settings_str
                    }}
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            boards = response_data.get("data", {}).get("boards", [])
            if boards:
                columns = boards[0].get("columns", [])
                log_debug(f"Retrieved {len(columns)} columns from board {board_id}")
                return json.dumps(columns)
            else:
                return json.dumps([])

        except Exception as e:
            logger.error(f"Error retrieving columns from board {board_id}: {e}")
            return json.dumps([])

    def get_users(self) -> str:
        """
        Get all users in the Monday.com workspace.

        :return: A JSON string containing user information
        """
        try:
            query = """
            query {
                users {
                    id
                    name
                    email
                    title
                    photo_thumb
                    is_guest
                    enabled
                }
            }
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            users = response_data.get("data", {}).get("users", [])
            log_debug(f"Retrieved {len(users)} users from Monday.com")
            return json.dumps(users)

        except Exception as e:
            logger.error(f"Error retrieving users: {e}")
            return json.dumps([])

    def create_update(self, item_id: str, body: str) -> str:
        """
        Create an update (comment) on an item.

        :param item_id: The ID of the item to comment on
        :param body: The text content of the update
        :return: A JSON string with the created update details
        """
        try:
            query = f"""
            mutation {{
                create_update (
                    item_id: {item_id},
                    body: "{body}"
                ) {{
                    id
                    body
                    created_at
                    creator {{
                        id
                        name
                    }}
                }}
            }}
            """

            data = {"query": query}
            response_data = self._make_nango_request("POST", "v2", data=data)

            update = response_data.get("data", {}).get("create_update", {})
            log_debug(f"Created update on item {item_id}")
            return json.dumps({
                "status": "success",
                "update": update
            })

        except Exception as e:
            logger.error(f"Error creating update on item {item_id}: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "item_id": item_id
            })