from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"^ws/chat/(?P<conversation_id>[0-9a-fA-F-]{36})/$",
        consumers.ChatConsumer.as_asgi(),
    ),
]
