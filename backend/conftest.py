"""Shared pytest fixtures."""

from __future__ import annotations

import datetime as dt

import pytest


@pytest.fixture
def operator(db, django_user_model):
    return django_user_model.objects.create_user(
        username="opsec", password="correct-horse-battery", callsign="opsec"
    )


@pytest.fixture
def engagement(db, operator):
    from apps.engagements.models import Engagement, EngagementStatus

    return Engagement.objects.create(
        name="Acme internal",
        slug="acme-internal",
        client="Acme",
        status=EngagementStatus.ACTIVE,
        authorized_cidrs=["10.4.0.0/16", "192.168.50.0/24"],
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2030, 1, 1),
        created_by=operator,
    )
