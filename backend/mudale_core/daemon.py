"""Background daemon management.

When the user exits the console, active tunnels keep running in a background
daemon process. The next console session reconnects to the daemon's state via
the shared SQLite database and PID file.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path.home() / ".mudale"
PID_FILE_NAME = "daemon.pid"
LOG_FILE_NAME = "daemon.log"


def get_pid_file(state_dir: Path | None = None) -> Path:
    return (state_dir or DEFAULT_STATE_DIR) / PID_FILE_NAME


def is_daemon_running(state_dir: Path | None = None) -> int | None:
    """Returns daemon PID if running, None otherwise."""
    pid_file = get_pid_file(state_dir)
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None

    try:
        os.kill(pid, 0)
        return pid
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return None
    except PermissionError:
        return pid


def start_daemon(state_dir: Path | None = None) -> int:
    """Fork a background daemon that keeps tunnels alive. Returns daemon PID."""
    state_dir = state_dir or DEFAULT_STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)

    existing = is_daemon_running(state_dir)
    if existing:
        return existing

    pid = os.fork()
    if pid > 0:
        time.sleep(0.3)
        return pid

    os.setsid()

    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)

    log_file = state_dir / LOG_FILE_NAME
    sys.stdin.close()
    sys.stdout = open(log_file, "a")  # noqa: SIM115
    sys.stderr = sys.stdout

    pid_file = get_pid_file(state_dir)
    pid_file.write_text(str(os.getpid()))

    _run_daemon_loop(state_dir)
    os._exit(0)


def stop_daemon(state_dir: Path | None = None) -> bool:
    """Stop the background daemon. Returns True if stopped."""
    pid = is_daemon_running(state_dir)
    if pid is None:
        return True

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.2)
        except ProcessLookupError:
            break

    pid_file = get_pid_file(state_dir)
    pid_file.unlink(missing_ok=True)
    return True


def _run_daemon_loop(state_dir: Path) -> None:
    """Main daemon loop — reconcile tunnels every 5 seconds."""
    from mudale_core.state import StateDB
    from mudale_core.supervisor import Engine

    db = StateDB(state_dir / "mudale.db")
    engine = Engine(db=db, state_dir=state_dir)

    running = True

    def handle_term(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)

    logger.info("Daemon started, PID %d", os.getpid())

    while running:
        try:
            engine.reconcile_once()
        except Exception:
            logger.exception("Reconcile error")
        time.sleep(5.0)

    logger.info("Daemon shutting down")
    engine.shutdown()
    get_pid_file(state_dir).unlink(missing_ok=True)
