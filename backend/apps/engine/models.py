"""Engine bookkeeping.

The engine daemon registers itself here so the web tier can show whether a
control plane is actually attached, and so a tunnel can record which daemon
instance owns its process.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.utils import timezone

#: An engine that has not heartbeated within this window is treated as gone.
HEARTBEAT_TIMEOUT = timedelta(seconds=30)


class EngineInstanceQuerySet(models.QuerySet):
    def alive(self) -> EngineInstanceQuerySet:
        return self.filter(last_heartbeat_at__gte=timezone.now() - HEARTBEAT_TIMEOUT)


class EngineInstance(models.Model):
    """One running ``manage.py enginectl`` process."""

    instance_id = models.CharField(max_length=64, unique=True)
    hostname = models.CharField(max_length=253, blank=True)
    pid = models.IntegerField(null=True, blank=True)
    version = models.CharField(max_length=32, blank=True)

    # Which adapters resolved their binaries at startup.
    capabilities = models.JSONField(default=dict, blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    last_heartbeat_at = models.DateTimeField(auto_now=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    objects = EngineInstanceQuerySet.as_manager()

    class Meta:
        ordering = ["-last_heartbeat_at"]

    def __str__(self) -> str:
        return f"{self.instance_id}@{self.hostname}"

    @property
    def is_alive(self) -> bool:
        if self.stopped_at is not None:
            return False
        return self.last_heartbeat_at >= timezone.now() - HEARTBEAT_TIMEOUT
