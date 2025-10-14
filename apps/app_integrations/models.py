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
    access_token = models.CharField(max_length=512)
    refresh_token = models.CharField(max_length=512, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
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
        Returns a valid access token, refreshing it if expired.
        """
        if self.expires_at and self.expires_at > now():
            return self.access_token

        if not self.refresh_token:
            raise Exception("No refresh token available.")

        print("🔄 Refreshing Google Drive access token...")

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

class NangoConnection(models.Model):
    user_id = models.BigIntegerField()
    # user_email = models.EmailField(max_length=255, blank=True, null=True)
    connection_id = models.CharField(max_length=255)
    provider = models.CharField(max_length=255)
    
    # JIRA-specific fields
    base_url = models.URLField(max_length=500, blank=True, null=True, help_text="JIRA instance base URL (e.g., https://benheath.atlassian.net)")
    cloud_id = models.CharField(max_length=255, blank=True, null=True, help_text="JIRA cloud ID for API calls")
    account_id = models.CharField(max_length=255, blank=True, null=True, help_text="JIRA account ID")
    subdomain = models.CharField(max_length=255, blank=True, null=True, help_text="JIRA subdomain (e.g., benheath)")
    
    # Additional metadata for other providers
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional provider-specific data")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nango_connection'

    def __str__(self):
        return f"NangoConnection {self.id} - {self.provider}"
    
    def get_jira_cloud_id(self):
        """
        Get the JIRA cloud ID, fetching it if not stored locally.
        """
        if self.cloud_id:
            return self.cloud_id
        
        # If cloud_id is not stored, we could fetch it here
        # For now, return None and let the calling code handle it
        return None
    
    def get_jira_base_url(self):
        """
        Get the JIRA base URL, constructing it from subdomain if needed.
        """
        if self.base_url:
            return self.base_url
        
        if self.subdomain:
            return f"https://{self.subdomain}.atlassian.net"
        
        return None
