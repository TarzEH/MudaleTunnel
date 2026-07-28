"""WebSocket URL routing.

Consumers are added per app as the live views land. Kept in its own module so
``asgi.py`` does not import app code before the Django app registry is ready.
"""

from django.urls import path

websocket_urlpatterns: list[path] = []
