import json
import requests
from os import getenv
from typing import Any, List, Optional, Dict
from django.conf import settings

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

class SharePointTools(Toolkit):
    def __init__(
        self,
        connection_id: Optional[str] = None,
        provider_config_key: str = "sharepoint",
        nango_host: Optional[str] = None,
        nango_secret_key: Optional[str] = None,
        nango_connection: Optional[object] = None,
        **kwargs,
    ):
        self.connection_id = connection_id or getenv("SHAREPOINT_CONNECTION_ID")
        self.provider_config_key = provider_config_key
        self.nango_host = nango_host or getattr(settings, 'NANGO_HOST', 'https://nango.opie.sh')
        self.nango_secret_key = nango_secret_key or getattr(settings, 'NANGO_SECRET_KEY', None)
        self.nango_connection = nango_connection

        if not self.connection_id:
            raise ValueError("SharePoint connection_id not provided. Please configure Nango integration first.")
        if not self.nango_secret_key:
            raise ValueError("NANGO_SECRET_KEY not configured.")

        super().__init__(name="sharepoint_tools", **kwargs)

        # Register methods as Agno tools
        self.register(self.list_sites)
        self.register(self.list_drives)
        self.register(self.list_items)
        self.register(self.get_item)
        self.register(self.create_item)
        self.register(self.update_item)
        self.register(self.delete_item)

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

    def list_sites(self) -> str:
        """List all SharePoint sites accessible to the user."""
        try:
            endpoint = "graph/v1.0/sites?search=*"
            data = self._make_nango_request("GET", endpoint)
            sites = data.get("value", [])
            return json.dumps(sites)
        except Exception as e:
            logger.error(f"Error listing SharePoint sites: {e}")
            return json.dumps([])

    def list_drives(self, site_id: str) -> str:
        """List all document libraries (drives) for a given site."""
        try:
            endpoint = f"graph/v1.0/sites/{site_id}/drives"
            data = self._make_nango_request("GET", endpoint)
            drives = data.get("value", [])
            return json.dumps(drives)
        except Exception as e:
            logger.error(f"Error listing SharePoint drives: {e}")
            return json.dumps([])

    def list_items(self, drive_id: str, folder_id: Optional[str] = None) -> str:
        """List items in a drive or folder."""
        try:
            if folder_id:
                endpoint = f"graph/v1.0/drives/{drive_id}/items/{folder_id}/children"
            else:
                endpoint = f"graph/v1.0/drives/{drive_id}/root/children"
            data = self._make_nango_request("GET", endpoint)
            items = data.get("value", [])
            return json.dumps(items)
        except Exception as e:
            logger.error(f"Error listing SharePoint items: {e}")
            return json.dumps([])

    def get_item(self, drive_id: str, item_id: str) -> str:
        """Get details for a specific item (file or folder)."""
        try:
            endpoint = f"graph/v1.0/drives/{drive_id}/items/{item_id}"
            data = self._make_nango_request("GET", endpoint)
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error getting SharePoint item: {e}")
            return json.dumps({})

    def create_item(self, drive_id: str, parent_id: str, name: str, content: Optional[str] = None, is_folder: bool = False) -> str:
        """
        Create a file or folder in SharePoint.
        If is_folder is True, creates a folder. Otherwise, creates a file with the given content.
        """
        try:
            if is_folder:
                endpoint = f"graph/v1.0/drives/{drive_id}/items/{parent_id}/children"
                data = {
                    "name": name,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename"
                }
                created = self._make_nango_request("POST", endpoint, data=data)
            else:
                endpoint = f"graph/v1.0/drives/{drive_id}/items/{parent_id}:/{name}:/content"
                headers = {
                    "Authorization": f"Bearer {self.nango_secret_key}",
                    "Connection-Id": self.connection_id,
                    "Provider-Config-Key": self.provider_config_key,
                    "Accept": "application/json",
                    "Content-Type": "text/plain"
                }
                url = f"{self.nango_host}/proxy/{endpoint.lstrip('/')}"
                response = requests.put(url, headers=headers, data=content or "")
                response.raise_for_status()
                created = response.json()
            return json.dumps(created)
        except Exception as e:
            logger.error(f"Error creating SharePoint item: {e}")
            return json.dumps({"error": str(e)})

    def update_item(self, drive_id: str, item_id: str, updates: Dict[str, Any]) -> str:
        """Update metadata for a file or folder."""
        try:
            endpoint = f"graph/v1.0/drives/{drive_id}/items/{item_id}"
            data = self._make_nango_request("PATCH", endpoint, data=updates)
            return json.dumps(data)
        except Exception as e:
            logger.error(f"Error updating SharePoint item: {e}")
            return json.dumps({"error": str(e)})

    def delete_item(self, drive_id: str, item_id: str) -> str:
        """Delete a file or folder."""
        try:
            endpoint = f"graph/v1.0/drives/{drive_id}/items/{item_id}"
            self._make_nango_request("DELETE", endpoint)
            return json.dumps({"status": "deleted"})
        except Exception as e:
            logger.error(f"Error deleting SharePoint item: {e}")
            return json.dumps({"error": str(e)})