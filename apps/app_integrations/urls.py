# app_integrations/urls.py
from django.urls import path
from .views import google_oauth_start, google_oauth_callback

urlpatterns = [
    path("google/oauth/start/", google_oauth_start, name="google_oauth_start"),
    path("google/oauth/callback/", google_oauth_callback, name="google_oauth_callback"),
]
