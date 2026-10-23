"""ASGI entry point.

WebSocket connections go through ``AllowedHostsOriginValidator``, which rejects
a handshake whose ``Origin`` is not in ``ALLOWED_HOSTS``/``CSRF_TRUSTED_ORIGINS``.
That check is the reason a page on an unrelated site cannot open a socket to the
dashboard and read live tunnel state — the previous generation of this tool
accepted every handshake unconditionally.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mudale.settings.prod")

from django.core.asgi import get_asgi_application  # noqa: E402

# Instantiated before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from mudale.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
