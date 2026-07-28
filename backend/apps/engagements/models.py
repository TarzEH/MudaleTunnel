"""Engagements — the unit of authorisation and the parent of all operational data.

Every agent, tunnel, route and scan belongs to exactly one engagement, and every
target is checked against that engagement's ``authorized_cidrs`` before the
engine acts on it. Deleting an engagement cascades to its operational records.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.engagements import scope


class EngagementStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    CLOSED = "closed", "Closed"


class MembershipRole(models.TextChoices):
    LEAD = "lead", "Lead"
    OPERATOR = "operator", "Operator"
    OBSERVER = "observer", "Observer"


def validate_cidr_list(value: list[str]) -> None:
    """Field-level validator: every entry must parse as a network."""
    try:
        scope.networks_from_strings(list(value or []))
    except scope.ScopeViolation as exc:
        raise ValidationError(str(exc)) from exc


class EngagementQuerySet(models.QuerySet):
    def operational(self) -> EngagementQuerySet:
        """Engagements the engine is allowed to act for."""
        return self.filter(status=EngagementStatus.ACTIVE)

    def visible_to(self, operator) -> EngagementQuerySet:
        if operator.is_admin:
            return self
        return self.filter(memberships__operator=operator).distinct()


class Engagement(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64, unique=True)
    client = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=16, choices=EngagementStatus.choices, default=EngagementStatus.PLANNED
    )

    # The authorisation allowlist. Empty means nothing is in scope — a new
    # engagement is inert until someone deliberately widens it.
    authorized_cidrs = ArrayField(
        models.CharField(max_length=64),
        default=list,
        blank=True,
        validators=[validate_cidr_list],
        help_text="CIDR ranges this engagement is authorised to touch, e.g. 10.4.0.0/16",
    )

    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="engagements_created",
    )

    objects = EngagementQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_on__isnull=True)
                | models.Q(starts_on__isnull=True)
                | models.Q(ends_on__gte=models.F("starts_on")),
                name="engagement_ends_after_start",
            )
        ]

    def __str__(self) -> str:
        return self.name

    # ── Scope ───────────────────────────────────────────────────────────

    @property
    def allowed_networks(self) -> list[scope.IPNetwork]:
        return scope.networks_from_strings(self.authorized_cidrs)

    @property
    def is_operational(self) -> bool:
        """Whether the engine may act for this engagement right now."""
        if self.status != EngagementStatus.ACTIVE:
            return False
        today = timezone.localdate()
        if self.starts_on and today < self.starts_on:
            return False
        if self.ends_on and today > self.ends_on:
            return False
        return True

    def assert_operational(self) -> None:
        if not self.is_operational:
            raise scope.ScopeViolation(
                f"Engagement {self.slug!r} is not operational "
                f"(status={self.status}, window={self.starts_on}..{self.ends_on})"
            )

    def check_network(self, target: str) -> scope.IPNetwork:
        """Validate a CIDR/address target for this engagement."""
        self.assert_operational()
        return scope.assert_network_in_scope(target, self.allowed_networks)

    def check_host(self, target: str, *, resolve: bool = True):
        """Validate an address-or-hostname target for this engagement."""
        self.assert_operational()
        return scope.assert_host_in_scope(target, self.allowed_networks, resolve=resolve)


class EngagementMembership(models.Model):
    engagement = models.ForeignKey(
        Engagement, on_delete=models.CASCADE, related_name="memberships"
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="engagement_memberships"
    )
    role = models.CharField(
        max_length=16, choices=MembershipRole.choices, default=MembershipRole.OPERATOR
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "operator"], name="unique_membership_per_engagement"
            )
        ]
        ordering = ["engagement", "operator"]

    def __str__(self) -> str:
        return f"{self.operator} @ {self.engagement} ({self.role})"

    @property
    def can_mutate(self) -> bool:
        return self.role in {MembershipRole.LEAD, MembershipRole.OPERATOR}
