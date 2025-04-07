import hashlib
import hmac
import os
import time
from functools import wraps

from django.http import HttpResponseForbidden

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

def slack_verified(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        slack_signature = request.headers.get("X-Slack-Signature")

        if not timestamp or not slack_signature:
            return HttpResponseForbidden("Missing Slack signature or timestamp")

        # protect against replay attacks
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return HttpResponseForbidden("Slack request timestamp too old")

        sig_basestring = f"v0:{timestamp}:{request.body.decode('utf-8')}"
        my_signature = (
            "v0=" + hmac.new(
                SLACK_SIGNING_SECRET.encode(),
                sig_basestring.encode(),
                hashlib.sha256
            ).hexdigest()
        )

        if not hmac.compare_digest(my_signature, slack_signature):
            return HttpResponseForbidden("Invalid Slack signature")

        return view_func(request, *args, **kwargs)
    return _wrapped_view