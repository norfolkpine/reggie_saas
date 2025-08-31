import requests
from django.conf import settings
from django.db import models
from django.utils.timezone import now, timedelta


class SupportedApp(models.Model):
    key = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon_url = models.URLField(blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class ConnectedApp(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connected_apps")
    app = models.ForeignKey(SupportedApp, on_delete=models.CASCADE, related_name="connected_apps")
    
    # Legacy OAuth fields (kept for backward compatibility)
    access_token = models.CharField(max_length=512, blank=True)
    refresh_token = models.CharField(max_length=512, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Nango integration fields
    nango_connection_id = models.CharField(max_length=255, blank=True, db_index=True,
                                          help_text="Nango connection ID for this integration")
    use_nango = models.BooleanField(default=True, 
                                   help_text="Whether to use Nango for this connection")
    
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "app")

    def __str__(self):
        return f"{self.user.email} - {self.get_app_display()}"

    def is_expired(self):
        return self.expires_at and now() >= self.expires_at

    def get_valid_token(self):
        """
        Returns a valid access token, using Nango or legacy method.
        """
        # Use Nango if enabled and connection ID exists
        if self.use_nango and self.nango_connection_id:
            from apps.app_integrations.services import get_nango_service
            nango = get_nango_service()
            
            token = nango.get_token(
                connection_id=self.nango_connection_id,
                provider_config_key=self.app.key
            )
            
            if token:
                return token
            else:
                raise Exception(f"Failed to get token from Nango for connection {self.nango_connection_id}")
        
        # Fallback to legacy OAuth flow
        if self.expires_at and self.expires_at > now():
            return self.access_token

        if not self.refresh_token:
            raise Exception("No refresh token available.")

        print("🔄 Refreshing Google Drive access token (legacy)...")

        data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            res = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=10)
            res.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to refresh token: {str(e)}")

        token_data = res.json()
        self.access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        self.expires_at = now() + timedelta(seconds=expires_in) if expires_in else None
        self.metadata.update(
            {
                "scope": token_data.get("scope"),
                "token_type": token_data.get("token_type"),
            }
        )
        self.save(update_fields=["access_token", "expires_at", "metadata"])

        return self.access_token
    
    def make_api_request(self, method, endpoint, **kwargs):
        """
        Make an API request through Nango or directly.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            Response data
        """
        if self.use_nango and self.nango_connection_id:
            from apps.app_integrations.services import get_nango_service
            nango = get_nango_service()
            
            return nango.proxy_request(
                connection_id=self.nango_connection_id,
                provider_config_key=self.app.key,
                method=method,
                endpoint=endpoint,
                data=kwargs.get('json'),
                params=kwargs.get('params')
            )
        else:
            # Legacy direct API call
            token = self.get_valid_token()
            headers = kwargs.get('headers', {})
            headers['Authorization'] = f'Bearer {token}'
            
            response = requests.request(
                method=method,
                url=endpoint,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
