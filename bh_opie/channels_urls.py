from apps.group_chat.routing import websocket_urlpatterns as group_chat_patterns
from apps.opie.routing import http_urlpatterns as opie_http_patterns
from apps.opie.routing import websocket_urlpatterns as opie_websocket_patterns

# Combine all websocket patterns
websocket_urlpatterns = [] + group_chat_patterns + opie_websocket_patterns

# HTTP patterns (for streaming)
http_urlpatterns = [] + opie_http_patterns

# Combined urlpatterns for the ASGI router
urlpatterns = websocket_urlpatterns + http_urlpatterns
