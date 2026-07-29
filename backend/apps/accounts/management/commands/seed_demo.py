"""Create a ready-to-use operator, engagement and API key.

    python manage.py seed_demo

Exists so a fresh checkout is usable in one command instead of a
createsuperuser prompt followed by clicking through the UI to define scope.

Refuses to run on a deployment that is reachable from anywhere but loopback:
seeding a known password into a console that opens tunnels into client networks
would be indefensible, and "it was only meant for the demo" is exactly how that
ends up in production.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import ApiKey, Operator, Role
from apps.engagements.models import (
    Engagement,
    EngagementMembership,
    EngagementStatus,
    MembershipRole,
)

DEFAULT_USERNAME = "operator"
DEFAULT_PASSWORD = "mudale-demo-2026"  # noqa: S105 - a documented demo value, loopback only
DEFAULT_SLUG = "lab"


class Command(BaseCommand):
    help = "Seed a demo operator, engagement and API key (loopback deployments only)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=DEFAULT_USERNAME)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--engagement", default="Local lab")
        parser.add_argument(
            "--cidr",
            action="append",
            default=None,
            help="Authorised CIDR. Repeatable. Defaults to loopback plus RFC1918 lab space.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even if the deployment is not loopback-only. Do not use.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["force"] and not self._is_loopback_only():
            raise CommandError(
                f"ALLOWED_HOSTS is {settings.ALLOWED_HOSTS}, which is reachable beyond "
                f"loopback. Refusing to seed a known password. Use createsuperuser instead."
            )

        cidrs = options["cidr"] or ["127.0.0.0/8", "10.4.0.0/16", "192.168.50.0/24"]

        operator, created = Operator.objects.get_or_create(
            username=options["username"],
            defaults={
                "role": Role.ADMIN,
                "callsign": options["username"],
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            operator.set_password(options["password"])
            operator.save(update_fields=["password"])

        engagement, _ = Engagement.objects.get_or_create(
            slug=DEFAULT_SLUG,
            defaults={
                "name": options["engagement"],
                "client": "self",
                "status": EngagementStatus.ACTIVE,
                "authorized_cidrs": cidrs,
                "created_by": operator,
            },
        )
        EngagementMembership.objects.get_or_create(
            engagement=engagement,
            operator=operator,
            defaults={"role": MembershipRole.LEAD},
        )

        ApiKey.objects.filter(operator=operator, name="cli").delete()
        _, raw_key = ApiKey.issue(operator=operator, name="cli")

        self.stdout.write(self.style.SUCCESS("Demo environment ready.\n"))
        self.stdout.write("  dashboard   http://127.0.0.1:8000")
        self.stdout.write(f"  username    {operator.get_username()}")
        self.stdout.write(
            f"  password    {options['password'] if created else '(unchanged — user existed)'}"
        )
        self.stdout.write(f"  engagement  [{engagement.pk}] {engagement.name}")
        self.stdout.write(f"  scope       {', '.join(engagement.authorized_cidrs)}\n")
        self.stdout.write("  CLI:")
        self.stdout.write(f"    mudale login --url http://127.0.0.1:8000 --token {raw_key}\n")

    @staticmethod
    def _is_loopback_only() -> bool:
        allowed = {host.strip().lower() for host in settings.ALLOWED_HOSTS}
        # "0.0.0.0" is how a container binds, not a route in from elsewhere;
        # the published port is what decides reachability, and compose binds it
        # to loopback.
        loopback = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}  # noqa: S104
        return bool(allowed) and allowed <= loopback
