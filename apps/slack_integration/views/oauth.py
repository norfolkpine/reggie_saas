from django.conf import settings
from django.shortcuts import redirect


def slack_oauth_start(request):
    scopes = ["app_mentions:read", "chat:write"]
    redirect_uri = settings.SLACK_REDIRECT_URI
    scope_str = ",".join(scopes)
    install_url = (
        f"https://slack.com/oauth/v2/authorize?client_id={settings.SLACK_CLIENT_ID}&"
        f"scope={scope_str}&redirect_uri={redirect_uri}"
    )
    return redirect(install_url)
