"""v1 API routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api import views

router = DefaultRouter()
router.register("engagements", views.EngagementViewSet, basename="engagement")
router.register("agents", views.AgentViewSet, basename="agent")
router.register("tunnels", views.TunnelViewSet, basename="tunnel")
router.register("scans", views.ScanViewSet, basename="scan")
router.register("services", views.ServiceViewSet, basename="service")
router.register("audit", views.AuditEventViewSet, basename="audit")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("bootstrap/", views.bootstrap, name="bootstrap"),
    path("me/", views.me, name="me"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("engine/status/", views.engine_status, name="engine-status"),
    path("pivot/map/", views.pivot_map, name="pivot-map"),
    path("", include(router.urls)),
]
