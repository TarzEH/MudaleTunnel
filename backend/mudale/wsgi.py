"""WSGI entry point.

Only useful for management tooling and simple health checks — the real server is
ASGI (see ``mudale.asgi``) because the dashboard needs WebSockets.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mudale.settings.prod")

application = get_wsgi_application()
