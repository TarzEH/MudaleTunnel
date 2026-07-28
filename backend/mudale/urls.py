"""Root URL configuration.

``/api/`` is the only surface the React SPA talks to. ``/admin/`` is kept because
Django's admin is a genuinely useful read-only console for the audit trail, but
it is namespaced under an env-configurable path so it is not sitting on a
guessable URL in a deployment reachable from a client network.
"""

from django.contrib import admin
from django.urls import include, path

from mudale.settings.env import env_str

ADMIN_PATH = env_str("MUDALE_ADMIN_PATH", default="admin").strip("/")

urlpatterns = [
    path(f"{ADMIN_PATH}/", admin.site.urls),
    path("api/", include("mudale.api_urls")),
]

admin.site.site_header = "MudaleTunnel"
admin.site.site_title = "MudaleTunnel"
admin.site.index_title = "Control plane"
