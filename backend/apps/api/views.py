"""API view sets.

Every queryset is filtered by engagement membership, so an operator cannot read
another team's engagement by guessing an id. Every mutation delegates to the
service layer rather than saving directly — that is what keeps scope checks and
audit writes on the path of *all* callers, API and CLI alike.
"""

from __future__ import annotations

import logging

from django.contrib.auth import authenticate, login, logout
from django.db.models import Count
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.agents.models import Agent
from apps.api.permissions import IsOperatorOrReadOnly
from apps.api.serializers import (
    AgentSerializer,
    AuditEventSerializer,
    EngagementSerializer,
    ListenerCreateSerializer,
    ListenerSerializer,
    MeSerializer,
    RouteCreateSerializer,
    RouteSerializer,
    ScanCreateSerializer,
    ScanSerializer,
    ServiceSerializer,
    TunnelCreateSerializer,
    TunnelLogSerializer,
    TunnelSerializer,
)
from apps.audit.middleware import context_for
from apps.audit.models import AuditAction, AuditEvent
from apps.audit.services import record
from apps.engagements.models import Engagement
from apps.scans import services as scan_services
from apps.scans.models import Scan, Service
from apps.tunnels import services as tunnel_services
from apps.tunnels.models import Listener, Route, Tunnel, TunnelLog

logger = logging.getLogger(__name__)

DEFAULT_LOG_LIMIT = 200
MAX_LOG_LIMIT = 2000


class EngagementScopedMixin:
    """Restricts a queryset to engagements the caller is a member of."""

    engagement_field = "engagement"

    def visible_engagements(self):
        return Engagement.objects.visible_to(self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            **{f"{self.engagement_field}__in": self.visible_engagements()}
        )

    def audit_context(self):
        return context_for(self.request)


# ── Engagements ─────────────────────────────────────────────────────────


class EngagementViewSet(viewsets.ModelViewSet):
    serializer_class = EngagementSerializer
    permission_classes = [IsOperatorOrReadOnly]
    filterset_fields = ["status"]
    search_fields = ["name", "client", "slug"]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        return (
            Engagement.objects.visible_to(self.request.user)
            .annotate(
                tunnel_count=Count("tunnels", distinct=True),
                scan_count=Count("scans", distinct=True),
                agent_count=Count("agents", distinct=True),
            )
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        engagement = serializer.save(created_by=self.request.user)
        record(
            AuditAction.ENGAGEMENT_CREATED,
            engagement=engagement,
            obj=engagement,
            payload={"authorized_cidrs": engagement.authorized_cidrs},
            context=context_for(self.request),
        )

    def perform_update(self, serializer):
        previous = list(serializer.instance.authorized_cidrs)
        engagement = serializer.save()
        context = context_for(self.request)

        if previous != engagement.authorized_cidrs:
            # Scope changes get their own action: widening what an engagement may
            # touch is the single most consequential edit in the system.
            record(
                AuditAction.ENGAGEMENT_SCOPE_CHANGED,
                engagement=engagement,
                obj=engagement,
                message=f"{previous} → {engagement.authorized_cidrs}",
                payload={"before": previous, "after": engagement.authorized_cidrs},
                context=context,
            )
        else:
            record(
                AuditAction.ENGAGEMENT_UPDATED,
                engagement=engagement,
                obj=engagement,
                context=context,
            )


# ── Agents ──────────────────────────────────────────────────────────────


class AgentViewSet(EngagementScopedMixin, viewsets.ModelViewSet):
    queryset = Agent.objects.all().order_by("name")
    serializer_class = AgentSerializer
    permission_classes = [IsOperatorOrReadOnly]
    filterset_fields = ["engagement", "engine", "status"]
    search_fields = ["name", "hostname", "remote_host"]

    def perform_create(self, serializer):
        agent = serializer.save(created_by=self.request.user)
        record(
            AuditAction.AGENT_REGISTERED,
            engagement=agent.engagement,
            obj=agent,
            context=context_for(self.request),
        )


# ── Tunnels ─────────────────────────────────────────────────────────────


class TunnelViewSet(EngagementScopedMixin, viewsets.ModelViewSet):
    queryset = (
        Tunnel.objects.select_related("engagement", "agent", "created_by")
        .prefetch_related("routes", "listeners")
        .order_by("-created_at")
    )
    serializer_class = TunnelSerializer
    permission_classes = [IsOperatorOrReadOnly]
    filterset_fields = ["engagement", "status", "kind", "desired_state", "agent"]
    search_fields = ["label"]

    def create(self, request, *args, **kwargs):
        payload = TunnelCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        engagement = self._require_visible(data["engagement"])

        tunnel = tunnel_services.create_tunnel(
            engagement=engagement,
            kind=data["kind"],
            spec=data["spec"],
            operator=request.user,
            agent=data.get("agent"),
            label=data.get("label", ""),
        )
        return Response(TunnelSerializer(tunnel).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Deleting a tunnel means asking the engine to stop it.

        The row is kept: a tunnel that existed is part of the engagement record,
        and removing it would leave audit entries pointing at nothing.
        """
        tunnel = self.get_object()
        tunnel_services.request_stop(tunnel, operator=request.user)
        return Response(TunnelSerializer(tunnel).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        tunnel = tunnel_services.request_stop(self.get_object(), operator=request.user)
        return Response(TunnelSerializer(tunnel).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        tunnel = tunnel_services.request_start(self.get_object(), operator=request.user)
        return Response(TunnelSerializer(tunnel).data)

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        tunnel = self.get_object()
        limit = min(int(request.query_params.get("limit", DEFAULT_LOG_LIMIT)), MAX_LOG_LIMIT)
        logs = TunnelLog.objects.filter(tunnel=tunnel).order_by("-created_at")[:limit]
        # Oldest first, so the dashboard can append without reversing.
        return Response({"results": TunnelLogSerializer(reversed(list(logs)), many=True).data})

    @action(detail=True, methods=["post"], url_path="routes")
    def add_route(self, request, pk=None):
        payload = RouteCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        route = tunnel_services.add_route(
            self.get_object(), payload.validated_data["cidr"], operator=request.user
        )
        return Response(RouteSerializer(route).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="listeners")
    def add_listener(self, request, pk=None):
        payload = ListenerCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        listener = tunnel_services.add_listener(
            self.get_object(), operator=request.user, **payload.validated_data
        )
        return Response(ListenerSerializer(listener).data, status=status.HTTP_201_CREATED)

    def _require_visible(self, engagement: Engagement) -> Engagement:
        if not Engagement.objects.visible_to(self.request.user).filter(pk=engagement.pk).exists():
            from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied

            raise DRFPermissionDenied("You are not a member of that engagement.")
        return engagement


class RouteViewSet(
    viewsets.GenericViewSet, viewsets.mixins.RetrieveModelMixin, viewsets.mixins.DestroyModelMixin
):
    queryset = Route.objects.select_related("tunnel__engagement")
    serializer_class = RouteSerializer
    permission_classes = [IsOperatorOrReadOnly]

    def get_queryset(self):
        return self.queryset.filter(
            tunnel__engagement__in=Engagement.objects.visible_to(self.request.user)
        )

    def destroy(self, request, *args, **kwargs):
        route = tunnel_services.remove_route(self.get_object(), operator=request.user)
        return Response(RouteSerializer(route).data)


class ListenerViewSet(
    viewsets.GenericViewSet, viewsets.mixins.RetrieveModelMixin, viewsets.mixins.DestroyModelMixin
):
    queryset = Listener.objects.select_related("tunnel__engagement")
    serializer_class = ListenerSerializer
    permission_classes = [IsOperatorOrReadOnly]

    def get_queryset(self):
        return self.queryset.filter(
            tunnel__engagement__in=Engagement.objects.visible_to(self.request.user)
        )

    def destroy(self, request, *args, **kwargs):
        listener = tunnel_services.remove_listener(self.get_object(), operator=request.user)
        return Response(ListenerSerializer(listener).data)


# ── Scans ───────────────────────────────────────────────────────────────


class ScanViewSet(EngagementScopedMixin, viewsets.ModelViewSet):
    queryset = Scan.objects.select_related("engagement", "requested_by").order_by("-queued_at")
    serializer_class = ScanSerializer
    permission_classes = [IsOperatorOrReadOnly]
    filterset_fields = ["engagement", "status", "profile"]
    search_fields = ["target"]

    def create(self, request, *args, **kwargs):
        payload = ScanCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        scan = scan_services.request_scan(
            engagement=data["engagement"],
            target=data["target"],
            profile=data["profile"],
            operator=request.user,
            via_tunnel=data.get("via_tunnel"),
        )
        return Response(ScanSerializer(scan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def services(self, request, pk=None):
        scan = self.get_object()
        queryset = Service.objects.filter(scan=scan).order_by("host", "port")
        page = self.paginate_queryset(queryset)
        serializer = ServiceSerializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class ServiceViewSet(EngagementScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.select_related("scan").order_by("host", "port")
    serializer_class = ServiceSerializer
    permission_classes = [IsOperatorOrReadOnly]
    filterset_fields = ["engagement", "scan", "protocol", "state", "port"]
    search_fields = ["host", "hostname", "service_name", "product"]


# ── Audit ───────────────────────────────────────────────────────────────


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only by construction: the model itself refuses writes."""

    serializer_class = AuditEventSerializer
    permission_classes = [IsOperatorOrReadOnly]
    filterset_fields = ["engagement", "action", "result", "object_type"]
    search_fields = ["message", "actor_label", "object_label"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        visible = Engagement.objects.visible_to(self.request.user)
        queryset = AuditEvent.objects.order_by("-created_at")
        if self.request.user.is_admin:
            return queryset
        # Non-admins see their engagements' events, plus engagement-less events
        # they themselves generated (logins, key issuance).
        from django.db.models import Q

        return queryset.filter(
            Q(engagement__in=visible) | Q(engagement__isnull=True, actor=self.request.user)
        )


# ── Session auth ────────────────────────────────────────────────────────


def _me_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.get_username(),
        "callsign": user.callsign,
        "role": user.role,
        "can_mutate": user.can_mutate,
        "is_admin": user.is_admin,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(MeSerializer(_me_payload(request.user)).data)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)

    if user is None:
        record(
            AuditAction.LOGIN_FAILED,
            result="denied",
            message=f"Failed login for {username[:64]!r}",
            context=context_for(request),
        )
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    login(request, user)
    request.user = user
    record(AuditAction.LOGIN, message="Signed in", context=context_for(request))
    return Response(MeSerializer(_me_payload(user)).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    record(AuditAction.LOGOUT, message="Signed out", context=context_for(request))
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Engine ──────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def engine_status(request):
    from apps.engine.models import EngineInstance

    instances = EngineInstance.objects.alive()
    return Response(
        {
            "attached": instances.exists(),
            "server_time": timezone.now(),
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


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Liveness probe. Reveals nothing about engagement data."""
    return Response({"status": "ok"})
