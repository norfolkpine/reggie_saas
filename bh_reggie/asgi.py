"""
ASGI config for Ben Heath SaaS project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from bh_reggie.channels_urls import http_urlpatterns, websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bh_reggie.settings")
# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()


class ChannelsHTTPRouter:
    """Router to direct certain HTTP paths to Channels consumers, falling back to Django for others"""

    def __init__(self, channels_http_router, django_asgi_app):
        self.channels_router = channels_http_router
        self.django_app = django_asgi_app

    async def __call__(self, scope, receive, send):
        # Check if this path is in our Channels routing
        try:
            # Let the URLRouter try to resolve the path
            # If it matches, it will handle the request
            # If it doesn't, it will raise an exception
            return await self.channels_router(scope, receive, send)
        except Exception:
            # Fall back to Django ASGI app for all other paths
            return await self.django_app(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": ChannelsHTTPRouter(URLRouter(http_urlpatterns), django_asgi_app),
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    websocket_urlpatterns,
                )
            )
        ),
    }
)
