"""The engine daemon.

    python manage.py enginectl

Runs as its own process, separate from the web server, because it owns
long-lived subprocesses. A gunicorn/daphne worker is recycled on deploys and
under load; a tunnel that lived inside one would be killed or orphaned by that.
Keeping the daemon separate means the web tier can restart freely while tunnels
stay up, and the daemon can restart and re-adopt what it finds.

It shares the Django ORM rather than talking to the API, so there is one
definition of the models and one migration history.
"""

from __future__ import annotations

import logging
import signal
import sys
import time

from django.core.management.base import BaseCommand
from django.db import OperationalError

from apps.engine.supervisor import VERSION, Supervisor

logger = logging.getLogger(__name__)

#: Back-off applied when the database is unreachable, so a restarting Postgres
#: does not turn into a hot loop of failed connections.
DB_RETRY_SECONDS = 5


class Command(BaseCommand):
    help = "Run the tunnel/scan engine: reconciles desired state and owns all subprocesses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--instance-id",
            default=None,
            help="Stable identifier for this engine. Defaults to hostname + random suffix.",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=None,
            help="Seconds between reconciliation passes (default: settings.ENGINE).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single pass and exit. Useful for tests and cron-style checks.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        interval = options["interval"] or float(settings.ENGINE["RECONCILE_INTERVAL_SECONDS"])
        supervisor = Supervisor(instance_id=options["instance_id"])

        self.stdout.write(self.style.SUCCESS(f"MudaleTunnel engine {VERSION}"))
        self.stdout.write(f"  instance     {supervisor.instance_id}")
        for name, available in supervisor.capabilities().items():
            marker = "ready" if available else "unavailable"
            self.stdout.write(f"  {name:<12} {marker}")

        supervisor.register()

        if options["once"]:
            supervisor.tick()
            supervisor.shutdown()
            return

        self._install_signal_handlers(supervisor)
        self.stdout.write(f"Reconciling every {interval:.0f}s. Ctrl-C to stop.\n")

        try:
            while not supervisor._stopping:
                started = time.monotonic()
                try:
                    supervisor.tick()
                except OperationalError as exc:
                    # Postgres restarted or is briefly unreachable. Keep the
                    # supervised processes running and try again shortly —
                    # losing the database is not a reason to drop live tunnels.
                    logger.warning(
                        "Database unavailable (%s); retrying in %ss", exc, DB_RETRY_SECONDS
                    )
                    time.sleep(DB_RETRY_SECONDS)
                    continue
                except Exception:
                    # A single bad row must never stop reconciliation.
                    logger.exception("Reconciliation pass failed; continuing")

                elapsed = time.monotonic() - started
                time.sleep(max(0.0, interval - elapsed))
        finally:
            supervisor.shutdown()

    def _install_signal_handlers(self, supervisor: Supervisor) -> None:
        def stop(signum, frame):
            name = signal.Signals(signum).name
            self.stdout.write(f"\nReceived {name}; stopping supervised processes...")
            supervisor._stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        if sys.platform != "win32":
            signal.signal(signal.SIGHUP, stop)
