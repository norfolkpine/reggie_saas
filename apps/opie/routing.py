from channels.auth import AuthMiddlewareStack
from django.urls import re_path

from .consumers import StreamAgentConsumer, VaultIngestionConsumer
from .vault_consumers import VaultStreamConsumer

# HTTP routes handled by channels
http_urlpatterns = [
    # Stream agent endpoint
    re_path(r"^opie/api/v1/chat/stream/", AuthMiddlewareStack(StreamAgentConsumer.as_asgi())),
    # Vault chat endpoint
    re_path(r"^opie/api/v1/vault/chat/stream/", AuthMiddlewareStack(VaultStreamConsumer.as_asgi())),
]

# Websocket routes
websocket_urlpatterns = [
    # Route for vault ingestion progress updates
    re_path(r"^ws/vault/ingestion/(?P<task_id>[0-9a-f-]+)/$", VaultIngestionConsumer.as_asgi()),
]
