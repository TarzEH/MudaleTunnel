"""Production settings.

Everything security-relevant is already hardened in base.py; this module's job
is to refuse to start when the deployment is misconfigured, rather than to
quietly run in a weak state.
"""

from mudale.settings.base import *  # noqa: F403
from mudale.settings.env import ImproperlyConfigured  # noqa: E402

DEBUG = False

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("MUDALE_ALLOWED_HOSTS must be set in production")

if "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("MUDALE_ALLOWED_HOSTS may not contain '*' in production")

if not DATABASES["default"]["PASSWORD"]:  # noqa: F405
    raise ImproperlyConfigured("MUDALE_DB_PASSWORD must be set in production")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
