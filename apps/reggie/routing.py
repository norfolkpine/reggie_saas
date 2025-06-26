from channels.auth import AuthMiddlewareStack
from django.urls import re_path

from .consumers import StreamAgentConsumer

# HTTP routes handled by channels
http_urlpatterns = [
    # Stream agent endpoint
    re_path(r"^reggie/api/v1/chat/stream/", AuthMiddlewareStack(StreamAgentConsumer.as_asgi())),
]

# Websocket routes
websocket_urlpatterns = [
    # Add any websocket routes here if needed
]
