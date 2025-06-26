from apps.group_chat.routing import websocket_urlpatterns as group_chat_patterns
from apps.reggie.routing import websocket_urlpatterns as reggie_websocket_patterns
from apps.reggie.routing import http_urlpatterns as reggie_http_patterns

# Combine all websocket patterns
websocket_urlpatterns = [] + group_chat_patterns + reggie_websocket_patterns

# HTTP patterns (for streaming)
http_urlpatterns = [] + reggie_http_patterns

# Combined urlpatterns for the ASGI router
urlpatterns = websocket_urlpatterns + http_urlpatterns
