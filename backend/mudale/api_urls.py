"""API routes. Versioned from the start so the SPA can be pinned to a contract."""

from django.urls import include, path

urlpatterns = [
    path("v1/", include(("mudale.api_v1", "v1"), namespace="v1")),
]
