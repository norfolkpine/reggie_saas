from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from slack_integration.bot.app import slack_handler

@csrf_exempt
def slack_events(request):
    return slack_handler.handle(request)
