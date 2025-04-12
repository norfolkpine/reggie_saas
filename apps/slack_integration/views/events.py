from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.slack_integration.bot.app import slack_handler


@csrf_exempt
def slack_events(request):
    try:
        print("Headers:", request.headers)
        print("Body:", request.body.decode())
        return slack_handler.handle(request)
    except Exception as e:
        print("Error handling request:", e)
        return HttpResponse(status=500)
