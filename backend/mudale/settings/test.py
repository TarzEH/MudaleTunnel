"""Test settings — fast hashing, in-memory channel layer, no external Redis."""

import os

os.environ.setdefault("MUDALE_SECRET_KEY", "test-only-not-a-secret")

from mudale.settings.base import *  # noqa: E402, F403

DEBUG = False

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Tests must never shell out to a real binary.
ENGINE = {  # noqa: F405
    **ENGINE,  # noqa: F405
    "SSH_BIN": "/nonexistent/ssh",
    "NMAP_BIN": "/nonexistent/nmap",
    "RECONCILE_INTERVAL_SECONDS": 0,
}
