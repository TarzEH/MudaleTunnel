"""Supervised child processes.

The engine owns every process it starts, for that process's whole life. The
rules that make that true:

* **Own process group.** Each child is started with ``start_new_session=True``,
  so it becomes a process-group leader. Stopping signals the *group*, which
  catches any helper the child forked (ssh's multiplexing, nmap's workers)
  rather than leaving strays behind.
* **No self-backgrounding.** Adapters never emit flags like ``ssh -f``, so the
  PID recorded here is the process that carries the tunnel, and it stays valid.
* **Reaped exactly once.** ``poll()`` reaps, and a reaped PID can be reused by
  the OS for an unrelated process. Signalling a stale PID is how you kill
  something you did not start, so the exit status is latched on first
  observation and never re-derived.
* **Escalation with a deadline.** SIGTERM, then SIGKILL after a grace period.
  Stop always terminates.

Output is drained on background threads. A process whose pipe buffer fills
blocks forever, which in v2's design would have looked exactly like a healthy
long-running tunnel.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)

#: Environment passed to every child, before adapter-specific additions.
#: Deliberately minimal — a child inheriting the daemon's full environment could
#: pick up credentials that have nothing to do with its job.
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "LANG": "C",
    "LC_ALL": "C",
    # Stops ssh and friends trying to open a GUI prompt.
    "DISPLAY": "",
}

DEFAULT_LOG_LINES = 500


class ProcessState(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    EXITED = "exited"


@dataclass
class ProcessOutcome:
    """The latched result of a finished process."""

    returncode: int
    stderr_tail: str
    stdout_tail: str
    #: True when the engine asked for the stop, so callers can distinguish a
    #: deliberate shutdown from a crash.
    requested: bool = False


@dataclass
class SupervisedProcess:
    """One child process, its output, and its lifecycle."""

    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    log_lines: int = DEFAULT_LOG_LINES
    #: Called for each output line, as (stream_name, line).
    on_output: Callable[[str, str], None] | None = None

    _popen: subprocess.Popen | None = field(default=None, init=False, repr=False)
    _outcome: ProcessOutcome | None = field(default=None, init=False, repr=False)
    _stop_requested: bool = field(default=False, init=False, repr=False)
    _stdout: deque[str] = field(default_factory=deque, init=False, repr=False)
    _stderr: deque[str] = field(default_factory=deque, init=False, repr=False)
    _readers: list[threading.Thread] = field(default_factory=list, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self) -> int:
        """Spawn the process and return its PID."""
        if self._popen is not None:
            raise RuntimeError("Process already started")

        self._stdout = deque(maxlen=self.log_lines)
        self._stderr = deque(maxlen=self.log_lines)

        self._popen = subprocess.Popen(  # noqa: S603 - argv is built by a validated adapter
            self.argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env={**BASE_ENV, **self.env},
            # Detach into a new session so the child leads its own process group
            # and does not receive signals aimed at the daemon's terminal.
            start_new_session=True,
            text=True,
            bufsize=1,
            close_fds=True,
        )

        self._start_reader("stdout", self._popen.stdout, self._stdout)
        self._start_reader("stderr", self._popen.stderr, self._stderr)

        logger.info("Started pid=%s %s", self._popen.pid, self.description or self.argv[0])
        return self._popen.pid

    @property
    def pid(self) -> int | None:
        return self._popen.pid if self._popen else None

    @property
    def state(self) -> ProcessState:
        if self._popen is None:
            return ProcessState.NOT_STARTED
        if self._outcome is not None:
            return ProcessState.EXITED
        return ProcessState.RUNNING

    def poll(self) -> ProcessOutcome | None:
        """Check whether the process has exited, latching the outcome once.

        Returns the outcome if it has finished, ``None`` while it is running.
        Safe to call repeatedly: after the first observed exit the latched value
        is returned without touching the (possibly recycled) PID again.
        """
        with self._lock:
            if self._outcome is not None:
                return self._outcome
            if self._popen is None:
                return None

            returncode = self._popen.poll()
            if returncode is None:
                return None

            self._outcome = self._latch(returncode)
            return self._outcome

    def stop(self, *, grace_seconds: float = 10.0) -> ProcessOutcome:
        """Terminate the process group, escalating to SIGKILL. Always terminates."""
        with self._lock:
            self._stop_requested = True
            if self._outcome is not None:
                return self._outcome
            if self._popen is None:
                raise RuntimeError("Process was never started")
            popen = self._popen

        self._signal_group(signal.SIGTERM)

        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if popen.poll() is not None:
                break
            time.sleep(0.05)
        else:
            logger.warning(
                "pid=%s did not exit within %.1fs of SIGTERM; sending SIGKILL",
                popen.pid,
                grace_seconds,
            )
            self._signal_group(signal.SIGKILL)
            try:
                popen.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - kernel-level stall
                logger.error("pid=%s survived SIGKILL", popen.pid)

        self._join_readers()

        with self._lock:
            if self._outcome is None:
                returncode = popen.returncode if popen.returncode is not None else -9
                self._outcome = self._latch(returncode)
            return self._outcome

    # ── Output ──────────────────────────────────────────────────────────

    def stdout_tail(self, limit: int | None = None) -> list[str]:
        lines = list(self._stdout)
        return lines[-limit:] if limit else lines

    def stderr_tail(self, limit: int | None = None) -> list[str]:
        lines = list(self._stderr)
        return lines[-limit:] if limit else lines

    # ── Internals ───────────────────────────────────────────────────────

    def _latch(self, returncode: int) -> ProcessOutcome:
        """Build the final outcome. Caller must hold the lock."""
        self._join_readers(timeout=1.0)
        return ProcessOutcome(
            returncode=returncode,
            stderr_tail="\n".join(self._stderr),
            stdout_tail="\n".join(self._stdout),
            requested=self._stop_requested,
        )

    def _signal_group(self, sig: signal.Signals) -> None:
        """Signal the child's whole process group.

        Falls back to signalling the process directly if the group has already
        gone, and treats "no such process" as success — the goal is that it is
        not running, and it is not.
        """
        popen = self._popen
        if popen is None or popen.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(popen.pid), sig)
        except ProcessLookupError:
            return
        except PermissionError:  # pragma: no cover - only if the child changed uid
            logger.error("Not permitted to signal process group of pid=%s", popen.pid)
        except OSError:
            try:
                popen.send_signal(sig)
            except (ProcessLookupError, OSError):
                return

    def _start_reader(self, name: str, stream, sink: deque) -> None:
        if stream is None:  # pragma: no cover - only when pipes are disabled
            return

        def pump() -> None:
            try:
                for line in stream:
                    text = line.rstrip("\n")
                    sink.append(text)
                    if self.on_output is not None:
                        try:
                            self.on_output(name, text)
                        except Exception:
                            logger.exception("Output callback failed for %s", name)
            except (ValueError, OSError):
                # Pipe closed while the process was tearing down.
                pass
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        thread = threading.Thread(target=pump, name=f"proc-{name}", daemon=True)
        thread.start()
        self._readers.append(thread)

    def _join_readers(self, timeout: float = 1.0) -> None:
        for thread in self._readers:
            thread.join(timeout=timeout)


def is_pid_alive(pid: int) -> bool:
    """Whether a PID currently exists.

    Only meaningful for a PID this process has *not* reaped — see the module
    docstring on PID reuse. Used by the reconciler when adopting processes
    recorded by a previous engine run.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, owned by someone else.
        return True
    return True
