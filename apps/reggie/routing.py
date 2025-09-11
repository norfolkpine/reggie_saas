from channels.auth import AuthMiddlewareStack
from django.urls import re_path

from .consumers import StreamAgentConsumer
from .views import VaultChatConsumer

# HTTP routes handled by channels
http_urlpatterns = [
    # Stream agent endpoint
    re_path(r"^reggie/api/v1/chat/stream/", AuthMiddlewareStack(StreamAgentConsumer.as_asgi())),
    # Vault AI assistant streaming endpoint
    re_path(r"^reggie/api/v1/vault/chat/stream/", AuthMiddlewareStack(VaultChatConsumer.as_asgi())),
]

# Websocket routes
websocket_urlpatterns = [
    # Add any websocket routes here if needed
]
