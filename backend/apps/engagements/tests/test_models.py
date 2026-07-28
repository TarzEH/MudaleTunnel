"""Engagement model behaviour — the authorisation gate, against a real database."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.engagements import scope
from apps.engagements.models import (
    Engagement,
    EngagementMembership,
    EngagementStatus,
    MembershipRole,
)

pytestmark = pytest.mark.django_db


def test_authorized_cidrs_round_trip(engagement):
    """ArrayField holds the allowlist and parses back into network objects."""
    engagement.refresh_from_db()
    assert engagement.authorized_cidrs == ["10.4.0.0/16", "192.168.50.0/24"]
    assert [str(n) for n in engagement.allowed_networks] == ["10.4.0.0/16", "192.168.50.0/24"]


def test_malformed_cidr_fails_validation(engagement):
    engagement.authorized_cidrs = ["10.4.0.0/16", "not-a-network"]
    with pytest.raises(ValidationError):
        engagement.full_clean()


def test_check_network_accepts_in_scope_target(engagement):
    assert str(engagement.check_network("10.4.9.0/24")) == "10.4.9.0/24"


def test_check_network_rejects_out_of_scope_target(engagement):
    with pytest.raises(scope.OutOfScope):
        engagement.check_network("172.16.0.0/24")


def test_check_network_rejects_flag_shaped_target(engagement):
    """The v2 injection payload, refused at the model boundary."""
    with pytest.raises(scope.TargetSyntaxError):
        engagement.check_network("-oN /etc/cron.d/pwn")


# ── Operational window ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [EngagementStatus.PLANNED, EngagementStatus.PAUSED, EngagementStatus.CLOSED],
)
def test_non_active_engagement_is_not_operational(engagement, status):
    """A paused or closed engagement must not be able to touch anything."""
    engagement.status = status
    engagement.save(update_fields=["status"])
    assert engagement.is_operational is False
    with pytest.raises(scope.ScopeViolation, match="not operational"):
        engagement.check_network("10.4.9.0/24")


def test_engagement_before_its_start_date_is_not_operational(engagement):
    engagement.starts_on = dt.date.today() + dt.timedelta(days=7)
    engagement.save(update_fields=["starts_on"])
    with pytest.raises(scope.ScopeViolation, match="not operational"):
        engagement.check_network("10.4.9.0/24")


def test_expired_engagement_is_not_operational(engagement):
    """An engagement whose authorisation window has closed stops working on its own."""
    engagement.starts_on = dt.date.today() - dt.timedelta(days=30)
    engagement.ends_on = dt.date.today() - dt.timedelta(days=1)
    engagement.save(update_fields=["starts_on", "ends_on"])
    with pytest.raises(scope.ScopeViolation, match="not operational"):
        engagement.check_network("10.4.9.0/24")


def test_engagement_with_no_dates_is_operational_while_active(operator):
    engagement = Engagement.objects.create(
        name="Open ended", slug="open-ended", status=EngagementStatus.ACTIVE,
        authorized_cidrs=["10.9.0.0/16"], created_by=operator,
    )
    assert engagement.is_operational is True


def test_new_engagement_is_inert(operator):
    """No authorised ranges means nothing is in scope — widening must be deliberate."""
    engagement = Engagement.objects.create(
        name="Fresh", slug="fresh", status=EngagementStatus.ACTIVE, created_by=operator
    )
    assert engagement.authorized_cidrs == []
    with pytest.raises(scope.OutOfScope, match="no authorised ranges"):
        engagement.check_network("10.4.9.0/24")


# ── Constraints ─────────────────────────────────────────────────────────


def test_end_date_before_start_date_is_refused_by_the_database(operator):
    with pytest.raises(IntegrityError), transaction.atomic():
        Engagement.objects.create(
            name="Backwards", slug="backwards", created_by=operator,
            starts_on=dt.date(2026, 6, 1), ends_on=dt.date(2026, 1, 1),
        )


def test_slug_is_unique(engagement, operator):
    with pytest.raises(IntegrityError), transaction.atomic():
        Engagement.objects.create(name="Duplicate", slug=engagement.slug, created_by=operator)


def test_operator_cannot_be_added_to_an_engagement_twice(engagement, operator):
    EngagementMembership.objects.create(engagement=engagement, operator=operator)
    with pytest.raises(IntegrityError), transaction.atomic():
        EngagementMembership.objects.create(engagement=engagement, operator=operator)


# ── Visibility ──────────────────────────────────────────────────────────


def test_operator_sees_only_engagements_they_belong_to(engagement, django_user_model):
    outsider = django_user_model.objects.create_user(username="outsider", password="x" * 16)
    assert Engagement.objects.visible_to(outsider).count() == 0

    EngagementMembership.objects.create(
        engagement=engagement, operator=outsider, role=MembershipRole.OBSERVER
    )
    assert list(Engagement.objects.visible_to(outsider)) == [engagement]


def test_admin_sees_every_engagement(engagement, django_user_model):
    admin = django_user_model.objects.create_superuser(username="root", password="x" * 16)
    assert list(Engagement.objects.visible_to(admin)) == [engagement]


def test_observer_cannot_mutate(engagement, operator):
    membership = EngagementMembership.objects.create(
        engagement=engagement, operator=operator, role=MembershipRole.OBSERVER
    )
    assert membership.can_mutate is False


def test_lead_and_operator_can_mutate(engagement, django_user_model):
    for index, role in enumerate((MembershipRole.LEAD, MembershipRole.OPERATOR)):
        user = django_user_model.objects.create_user(username=f"u{index}", password="x" * 16)
        membership = EngagementMembership.objects.create(
            engagement=engagement, operator=user, role=role
        )
        assert membership.can_mutate is True
