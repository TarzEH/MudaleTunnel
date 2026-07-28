"""Root URL configuration.

``/api/`` is the only surface the React SPA talks to. ``/admin/`` is kept because
Django's admin is a genuinely useful read-only console for the audit trail, but
it is namespaced under an env-configurable path so it is not sitting on a
guessable URL in a deployment reachable from a client network.
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path

from apps.api.spa import spa
from mudale.settings.env import env_str

ADMIN_PATH = env_str("MUDALE_ADMIN_PATH", default="admin").strip("/")

urlpatterns = [
    path(f"{ADMIN_PATH}/", admin.site.urls),
    path("api/", include("mudale.api_urls")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

# Must be last: this matches everything the patterns above did not, and hands it
# to the SPA's own router. Anchored to exclude /api/ and /static/ so an unknown
# API path still 404s instead of being answered with the dashboard shell and a
# 200 — which would make every client-side error look like a successful request.
urlpatterns += [
    re_path(r"^(?!api/|static/)(?P<path>.*)$", spa, name="spa"),
]

admin.site.site_header = "MudaleTunnel"
admin.site.site_title = "MudaleTunnel"
admin.site.index_title = "Control plane"
