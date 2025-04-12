from django.db import models
from django.conf import settings
from django.utils.timezone import now

class ConnectedApp(models.Model):
    GOOGLE_DRIVE = "google_drive"

    APP_CHOICES = [
        (GOOGLE_DRIVE, "Google Drive"),
        # Add more apps later
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connected_apps")
    app = models.CharField(max_length=50, choices=APP_CHOICES)
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
