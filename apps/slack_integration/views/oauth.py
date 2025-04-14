from urllib.parse import urlencode

import requests

# import timezone
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

from apps.slack_integration.models import SlackWorkspace
from apps.teams.models import Team


def slack_oauth_start(request):
    if not request.user.is_authenticated and hasattr(request, "team"):
        return HttpResponseForbidden("You must be logged in and belong to a team.")

    try:
        team_id = request.team.id
        request.session["team_id"] = team_id  # Optional but nice to have

        scopes = [
            # Write scopes
            "im:write",
            "mpim:write",
            "app_mentions:read",
            "channels:join",
            "channels:manage",
            "chat:write.customize",
            "chat:write.public",
            "chat:write",
            "files:write",
            "groups:write",
            "links:write",
            "pins:write",
            "reactions:write",
            "reminders:write",
            "usergroups:write",
            "users:write",
            "assistant:write",
            "commands",
            # Read scopes
            "channels:history",
            "groups:history",
            "im:history",
            "mpim:history",
            "im:read",
            "mpim:read",
            "channels:read",
            "files:read",
            "groups:read",
            "links:read",
            "pins:read",
            "reactions:read",
            "reminders:read",
            "team:read",
            "usergroups:read",
            "users:read",
            "users.profile:read",
        ]

        query_params = {
            "client_id": settings.SLACK_CLIENT_ID,
            "scope": ",".join(scopes),
            "redirect_uri": settings.SLACK_REDIRECT_URI,
            "state": str(team_id),
        }

        install_url = f"https://slack.com/oauth/v2/authorize?{urlencode(query_params)}"
        return redirect(install_url)
    except Exception as e:
        print(f"Error during OAuth start: {str(e)}")
        return HttpResponse(f"Error during OAuth start: {str(e)}", status=500)


@csrf_exempt
def slack_oauth_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")  # INTERNAL passed state from slack_oauth_start
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
            headers={"Content-Type": "application/x-www-form-urlencoded"},
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

        return redirect("/slack/success/")  # TODO: frontend success page

    except Exception as e:
        return HttpResponse(f"Error during authentication: {str(e)}", status=500)
