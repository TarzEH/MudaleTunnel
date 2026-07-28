"""Network scans and the services they discover.

A scan can be run directly or *through* a tunnel, which is the whole point of a
pivoting tool: discover the next hop's network from the foothold you already
have. ``via_tunnel`` records which one, so the topology graph knows which side
of the network a finding came from.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ScanProfile(models.TextChoices):
    """Named nmap argument sets.

    Operators pick a profile; they never supply raw nmap flags. The mapping from
    profile to argv lives in the engine (``apps.engine.adapters.nmap``) so that
    the only user-controlled value reaching the command line is a target that has
    already been parsed into an ``ipaddress`` object.
    """

    DISCOVERY = "discovery", "Host discovery (ping sweep)"
    QUICK = "quick", "Quick (top 100 ports)"
    STANDARD = "standard", "Standard (top 1000 + versions)"
    FULL = "full", "Full (all TCP ports + versions)"
    UDP_TOP = "udp_top", "UDP (top 100 ports)"


class ScanStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed out"


TERMINAL_SCAN_STATUSES = frozenset(
    {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED, ScanStatus.TIMED_OUT}
)


class ScanQuerySet(models.QuerySet):
    def pending(self) -> ScanQuerySet:
        return self.filter(status=ScanStatus.QUEUED)

    def finished(self) -> ScanQuerySet:
        return self.filter(status__in=TERMINAL_SCAN_STATUSES)


class Scan(models.Model):
    engagement = models.ForeignKey(
        "engagements.Engagement", on_delete=models.CASCADE, related_name="scans"
    )
    # Normalised at creation time from the parsed network object, so what is
    # stored is what the engine will run — not the raw operator input.
    target = models.CharField(max_length=64)
    profile = models.CharField(
        max_length=16, choices=ScanProfile.choices, default=ScanProfile.STANDARD
    )
    via_tunnel = models.ForeignKey(
        "tunnels.Tunnel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans",
        help_text="Tunnel the scan was routed through, if any.",
    )

    status = models.CharField(
        max_length=16, choices=ScanStatus.choices, default=ScanStatus.QUEUED, db_index=True
    )
    owner_engine_id = models.CharField(max_length=64, blank=True)
    pid = models.IntegerField(null=True, blank=True)

    # Raw output is kept for evidence; it is what gets attached to a report.
    raw_stdout = models.TextField(blank=True)
    raw_stderr = models.TextField(blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    error = models.TextField(blank=True)

    hosts_up = models.PositiveIntegerField(default=0)
    services_found = models.PositiveIntegerField(default=0)

    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans_requested",
    )

    objects = ScanQuerySet.as_manager()

    class Meta:
        ordering = ["-queued_at"]
        indexes = [models.Index(fields=["engagement", "-queued_at"])]

    def __str__(self) -> str:
        return f"{self.get_profile_display()} of {self.target}"

    @property
    def is_finished(self) -> bool:
        return self.status in TERMINAL_SCAN_STATUSES

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at or not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class Service(models.Model):
    """One open port found by a scan."""

    class State(models.TextChoices):
        OPEN = "open", "Open"
        FILTERED = "filtered", "Filtered"
        OPEN_FILTERED = "open|filtered", "Open|filtered"
        CLOSED = "closed", "Closed"

    class Protocol(models.TextChoices):
        TCP = "tcp", "TCP"
        UDP = "udp", "UDP"

    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="services")
    engagement = models.ForeignKey(
        "engagements.Engagement", on_delete=models.CASCADE, related_name="services"
    )

    host = models.GenericIPAddressField()
    hostname = models.CharField(max_length=253, blank=True)
    port = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(65535)]
    )
    protocol = models.CharField(max_length=8, choices=Protocol.choices, default=Protocol.TCP)
    state = models.CharField(max_length=16, choices=State.choices, default=State.OPEN)

    # Everything below is parsed from nmap output — display-only, never used to
    # build a command line.
    service_name = models.CharField(max_length=64, blank=True)
    product = models.CharField(max_length=128, blank=True)
    version = models.CharField(max_length=128, blank=True)
    extra_info = models.CharField(max_length=256, blank=True)

    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["host", "port"]
        indexes = [
            models.Index(fields=["engagement", "host"]),
            models.Index(fields=["scan", "host"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["scan", "host", "port", "protocol"], name="unique_service_per_scan"
            )
        ]

    def __str__(self) -> str:
        return f"{self.host}:{self.port}/{self.protocol} {self.service_name}".strip()

    @property
    def banner(self) -> str:
        return " ".join(part for part in (self.product, self.version, self.extra_info) if part)
