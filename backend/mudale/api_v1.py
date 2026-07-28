"""v1 API surface.

Routers are registered per app as those apps grow view sets. Health is here
because it must keep working even if every other app is misconfigured.
"""

from django.urls import path
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.engine.models import EngineInstance


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Liveness probe. Deliberately reveals nothing about the engagement data."""
    return Response({"status": "ok"})


@api_view(["GET"])
def engine_status(request):
    """Whether an engine daemon is attached and what it can drive."""
    instances = EngineInstance.objects.alive()
    return Response(
        {
            "attached": instances.exists(),
            "instances": [
                {
                    "instance_id": instance.instance_id,
                    "hostname": instance.hostname,
                    "version": instance.version,
                    "capabilities": instance.capabilities,
                    "last_heartbeat_at": instance.last_heartbeat_at,
                }
                for instance in instances
            ],
        }
    )


urlpatterns = [
    path("health/", health, name="health"),
    path("engine/status/", engine_status, name="engine-status"),
]
