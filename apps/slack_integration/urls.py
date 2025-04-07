from django.urls import path
from slack_integration.views import events, oauth

urlpatterns = [
    path("oauth/start/", oauth.slack_oauth_start, name="slack_oauth_start"),
    path("events/", events.slack_events, name="slack_events"),
]
