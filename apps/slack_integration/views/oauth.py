from urllib.parse import urlencode

import requests

# import timezone
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

from apps.slack_integration.models import SlackWorkspace
from apps.teams.models import Team


def slack_oauth_start(request):
    if request.user.is_authenticated and hasattr(request.user, 'team'):
        team_id = request.user.team.id
        request.session['team_id'] = team_id  # Optional but nice to have

        scopes = ["app_mentions:read", "chat:write"]
        query_params = {
            "client_id": settings.SLACK_CLIENT_ID,
            "scope": ",".join(scopes),
            "redirect_uri": settings.SLACK_REDIRECT_URI,
            "state": str(team_id),
        }

        install_url = f"https://slack.com/oauth/v2/authorize?{urlencode(query_params)}"
        return redirect(install_url)

@csrf_exempt
def slack_oauth_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state") # INTERNAL passed state from slack_oauth_start
    if not code:
        return HttpResponse("Authentication failed: No code received", status=400)

    try:
        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                # "redirect_uri": settings.SLACK_REDIRECT_URI, 
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        slack_data = response.json()
        if not slack_data.get("ok"):
            return HttpResponse(f"Slack OAuth failed: {slack_data.get('error')}", status=400)

        slack_team_id = slack_data["team"]["id"]
        slack_team_name = slack_data["team"]["name"]
        access_token = slack_data["access_token"]
        bot_user_id = slack_data.get("bot_user_id")

        try:
            team = Team.objects.get(id=state)
            SlackWorkspace.objects.update_or_create(
                team=team,
                slack_team_id=slack_team_id,
                slack_team_name=slack_team_name,
                access_token=access_token,
                bot_user_id=bot_user_id,
                # installed_at=timezone.now(),
            )
        except Team.DoesNotExist:
            return HttpResponse("Invalid team reference", status=400)

        return redirect("/slack/success/")

    except Exception as e:
        return HttpResponse(f"Error during authentication: {str(e)}", status=500)