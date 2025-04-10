from django.urls import path
from apps.slack_integration.views import events, oauth

urlpatterns = [
    path("oauth/start/", oauth.slack_oauth_start, name="slack_oauth_start"),
    path("oauth/callback/", oauth.slack_oauth_callback, name="slack_oauth_callback"),
    path("events/", events.slack_events, name="slack_events"),
]