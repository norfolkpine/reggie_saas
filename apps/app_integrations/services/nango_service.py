"""
Nango Integration Service for managing OAuth connections and API access.

This service provides a wrapper around Nango's API to handle:
- OAuth authentication flows
- Connection management
- Token retrieval and refresh
- API proxying
"""

import logging
import requests
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class NangoService:
    """Service for interacting with Nango API."""
    
    def __init__(self):
        """Initialize Nango service with configuration from settings."""
        self.secret_key = settings.NANGO_SECRET_KEY
        self.public_key = settings.NANGO_PUBLIC_KEY
        self.host = settings.NANGO_HOST.rstrip('/')
        
        if not self.secret_key or not self.public_key:
            raise ImproperlyConfigured(
                "NANGO_SECRET_KEY and NANGO_PUBLIC_KEY must be set in settings"
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    def create_connection(
        self, 
        connection_id: str,
        provider_config_key: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new connection in Nango.
        
        Args:
            connection_id: Unique identifier for this connection
            provider_config_key: The provider key (e.g., 'google-drive', 'slack')
            user_id: The user ID in your system
            metadata: Optional metadata to store with the connection
            
        Returns:
            Connection details from Nango
        """
        url = f"{self.host}/connection"
        
        data = {
            "connection_id": connection_id,
            "provider_config_key": provider_config_key,
            "metadata": metadata or {}
        }
        
        try:
            response = requests.post(url, json=data, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create Nango connection: {e}")
            raise
    
    def get_connection(self, connection_id: str, provider_config_key: str) -> Optional[Dict[str, Any]]:
        """
        Get connection details from Nango.
        
        Args:
            connection_id: The connection identifier
            provider_config_key: The provider key
            
        Returns:
            Connection details or None if not found
        """
        url = f"{self.host}/connection/{connection_id}"
        
        params = {"provider_config_key": provider_config_key}
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get Nango connection: {e}")
            return None
    
    def delete_connection(self, connection_id: str, provider_config_key: str) -> bool:
        """
        Delete a connection from Nango.
        
        Args:
            connection_id: The connection identifier
            provider_config_key: The provider key
            
        Returns:
            True if successful, False otherwise
        """
        url = f"{self.host}/connection/{connection_id}"
        
        params = {"provider_config_key": provider_config_key}
        
        try:
            response = requests.delete(url, params=params, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to delete Nango connection: {e}")
            return False
    
    def get_auth_url(
        self,
        provider_config_key: str,
        connection_id: str,
        redirect_uri: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate the OAuth authorization URL for a provider.
        
        Args:
            provider_config_key: The provider key
            connection_id: Unique identifier for this connection
            redirect_uri: Optional redirect URI after auth
            metadata: Optional metadata to pass through auth flow
            
        Returns:
            The authorization URL
        """
        params = {
            "public_key": self.public_key,
            "connection_id": connection_id,
            "provider_config_key": provider_config_key
        }
        
        if redirect_uri:
            params["redirect_uri"] = redirect_uri
            
        if metadata:
            params["params"] = metadata
        
        # Build auth URL
        auth_url = f"{self.host.replace('api.', 'app.')}/oauth/authorize"
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        
        return f"{auth_url}?{query_string}"
    
    def get_token(self, connection_id: str, provider_config_key: str) -> Optional[str]:
        """
        Get the current access token for a connection.
        
        Args:
            connection_id: The connection identifier
            provider_config_key: The provider key
            
        Returns:
            Access token or None if not found
        """
        connection = self.get_connection(connection_id, provider_config_key)
        if connection and 'credentials' in connection:
            return connection['credentials'].get('access_token')
        return None
    
    def proxy_request(
        self,
        connection_id: str,
        provider_config_key: str,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Proxy an API request through Nango.
        
        This handles token refresh automatically.
        
        Args:
            connection_id: The connection identifier
            provider_config_key: The provider key
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint to call
            data: Request body data
            params: Query parameters
            
        Returns:
            API response data
        """
        url = f"{self.host}/proxy/{provider_config_key}"
        
        headers = {
            **self.headers,
            "Connection-Id": connection_id,
            "Provider-Config-Key": provider_config_key
        }
        
        proxy_data = {
            "method": method.upper(),
            "endpoint": endpoint
        }
        
        if data:
            proxy_data["data"] = data
        if params:
            proxy_data["params"] = params
        
        try:
            response = requests.post(url, json=proxy_data, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to proxy request through Nango: {e}")
            raise
    
    def list_connections(
        self, 
        connection_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List all connections or specific connections.
        
        Args:
            connection_ids: Optional list of connection IDs to filter
            
        Returns:
            List of connection details
        """
        url = f"{self.host}/connections"
        
        params = {}
        if connection_ids:
            params["connection_ids"] = ",".join(connection_ids)
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json().get('connections', [])
        except requests.RequestException as e:
            logger.error(f"Failed to list Nango connections: {e}")
            return []
    
    def sync_connection(self, connection_id: str, provider_config_key: str) -> bool:
        """
        Trigger a sync for a connection (if provider supports syncing).
        
        Args:
            connection_id: The connection identifier
            provider_config_key: The provider key
            
        Returns:
            True if sync started successfully
        """
        url = f"{self.host}/sync/trigger"
        
        data = {
            "connection_id": connection_id,
            "provider_config_key": provider_config_key
        }
        
        try:
            response = requests.post(url, json=data, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to trigger sync: {e}")
            return False


# Singleton instance
_nango_service = None


def get_nango_service() -> NangoService:
    """Get or create the singleton Nango service instance."""
    global _nango_service
    if _nango_service is None:
        _nango_service = NangoService()
    return _nango_service