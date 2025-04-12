from django.shortcuts import render


def oauth_success(request):
    return render(request, "slack_integration/oauth_success.html", {"title": "Slack Integration Successful"})
