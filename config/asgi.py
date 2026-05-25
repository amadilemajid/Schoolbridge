"""
ASGI configuration for SchoolBridge.
Handles both HTTP (Django) and WebSocket (Channels) connections.
US-074: WebSocket endpoint for real-time notifications.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from channels.security.websocket import AllowedHostsOriginValidator
from notifications.consumers import NotificationConsumer
from django.urls import re_path

websocket_urlpatterns = [
    re_path(r'^ws/notifications/$', NotificationConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
