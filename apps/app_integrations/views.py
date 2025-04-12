from django.shortcuts import render

# Create your views here.
import requests
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.timezone import now, timedelta
from .models import ConnectedApp
from django.contrib.auth.decorators import login_required

@login_required
def google_oauth_start(request):
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode
    return redirect(f"{base_url}?{urlencode(params)}")

@login_required
def google_oauth_callback(request):
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Missing code", status=400)

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    token_response = requests.post(token_url, data=data).json()

    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")

    ConnectedApp.objects.update_or_create(
        user=request.user,
        app=ConnectedApp.GOOGLE_DRIVE,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": now() + timedelta(seconds=expires_in),
            "metadata": token_response,
        },
    )

    return HttpResponse("✅ Google Drive connected.")
