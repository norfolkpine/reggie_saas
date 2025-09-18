from channels.auth import AuthMiddlewareStack
from django.urls import re_path

from .consumers import StreamAgentConsumer
from .vault_consumers import VaultStreamConsumer

# HTTP routes handled by channels
http_urlpatterns = [
    # Stream agent endpoint
    re_path(r"^reggie/api/v1/chat/stream/", AuthMiddlewareStack(StreamAgentConsumer.as_asgi())),
    # Vault chat endpoint
    re_path(r"^reggie/api/v1/vault/chat/stream/", AuthMiddlewareStack(VaultStreamConsumer.as_asgi())),
]

# Websocket routes
websocket_urlpatterns = [
    # Add any websocket routes here if needed
]
