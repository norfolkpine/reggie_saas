import requests
from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.integrations.models import SlackIntegration
from apps.teams.models import Team


@method_decorator(csrf_exempt, name='dispatch')
class SlackOAuthCallbackView(View):
    def get(self, request):
        code = request.GET.get("code")

        if not code:
            return HttpResponseBadRequest("Missing code")

        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.SLACK_REDIRECT_URI,
            },
        )

        data = response.json()
        if not data.get("ok"):
            return JsonResponse(data, status=400)

        team_id = data["team"]["id"]
        team_name = data["team"]["name"]
        access_token = data["access_token"]
        bot_user_id = data.get("bot_user_id")

        team, _ = Team.objects.get_or_create(external_id=team_id, defaults={"name": team_name})

        SlackIntegration.objects.update_or_create(
            team=team,
            defaults={
                "team_id": team_id,
                "team_name": team_name,
                "access_token": access_token,
                "bot_user_id": bot_user_id,
            },
        )

        return JsonResponse(status=200)
