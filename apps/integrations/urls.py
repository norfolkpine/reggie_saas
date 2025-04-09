from django.urls import path

from .views import SlackOAuthCallbackView

urlpatterns = [
    path("slack/callback/", SlackOAuthCallbackView.as_view(), name="slack_oauth_callback"),
]
