"""WebSocket URL routing.

Kept in its own module so ``asgi.py`` does not import app code before the Django
app registry is ready.
"""

from django.urls import path

from apps.api.consumers import EngagementConsumer

websocket_urlpatterns = [
    path("ws/v1/engagements/<int:engagement_id>/", EngagementConsumer.as_asgi()),
]
