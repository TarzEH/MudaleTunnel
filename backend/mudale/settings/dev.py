"""Development settings — loopback only, relaxed transport security.

Deliberately does NOT relax authentication: the dashboard drives ssh/nmap, so
an unauthenticated dev server is the same liability as an unauthenticated prod
server on a shared network.
"""

import os

os.environ.setdefault("MUDALE_SECRET_KEY", "dev-only-not-a-secret-change-in-prod")

from mudale.settings.base import *  # noqa: E402, F403
from mudale.settings.env import env_list  # noqa: E402

DEBUG = True

ALLOWED_HOSTS = env_list(
    "MUDALE_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"]
)

# Vite dev server runs on 5173 and talks to Django on 8000.
CSRF_TRUSTED_ORIGINS = env_list(
    "MUDALE_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
)
WEBSOCKET_ALLOWED_ORIGINS = env_list(
    "MUDALE_WEBSOCKET_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
)

# No TLS in front of runserver, so these would break the dev login loop.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

INTERNAL_IPS = ["127.0.0.1"]
