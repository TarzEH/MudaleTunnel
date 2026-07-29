"""Tests for the process supervisor.

These run real subprocesses (``sh``/``python``) rather than mocks, because the
v2 defects were precisely in the gap between what the code assumed about process
lifecycle and what the OS actually does.
"""

from __future__ import annotations

import os
import signal
import sys
import time

import pytest

from apps.engine.process import ProcessState, SupervisedProcess, is_pid_alive

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process semantics")


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ── Basic lifecycle ─────────────────────────────────────────────────────


def test_short_process_exit_is_observed():
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "exit 3"])
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    outcome = proc.poll()
    assert outcome.returncode == 3
    assert proc.state is ProcessState.EXITED


def test_output_is_captured_on_both_streams():
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "echo out; echo err >&2; exit 0"])
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    outcome = proc.poll()
    assert "out" in outcome.stdout_tail
    assert "err" in outcome.stderr_tail


def test_state_before_start():
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "true"])
    assert proc.state is ProcessState.NOT_STARTED
    assert proc.pid is None
    assert proc.poll() is None


def test_starting_twice_is_refused():
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "sleep 5"])
    proc.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            proc.start()
    finally:
        proc.stop(grace_seconds=1)


# ── The v2 lifecycle bugs ───────────────────────────────────────────────


def test_outcome_is_latched_and_stable():
    """Repeated polling must not re-derive status from a reaped PID.

    Once reaped, the OS is free to hand that PID to an unrelated process;
    re-deriving from it is how a supervisor ends up signalling something it
    never started.
    """
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "exit 7"])
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    first = proc.poll()
    for _ in range(5):
        assert proc.poll() is first


def test_stop_after_natural_exit_is_idempotent():
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "exit 0"])
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    outcome = proc.stop(grace_seconds=1)
    assert outcome.returncode == 0


def test_stop_terminates_a_long_running_process():
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "sleep 300"])
    pid = proc.start()
    assert is_pid_alive(pid)

    outcome = proc.stop(grace_seconds=5)

    assert outcome.requested is True
    assert outcome.returncode != 0
    assert wait_until(lambda: not is_pid_alive(pid))


def test_sigterm_ignoring_process_is_killed():
    """A child that ignores SIGTERM must still be stopped, via SIGKILL.

    Uses a Python child rather than a shell ``trap``: shells differ in whether
    they keep an ignored disposition while waiting on a foreground child, and
    this test needs the ignore to be unambiguous.
    """
    script = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(300)"
    )
    proc = SupervisedProcess(argv=[sys.executable, "-c", script])
    pid = proc.start()
    # Give the child time to install the handler before signalling it.
    time.sleep(0.5)

    started = time.monotonic()
    outcome = proc.stop(grace_seconds=1.0)
    elapsed = time.monotonic() - started

    assert outcome.returncode == -signal.SIGKILL
    assert elapsed >= 1.0, "escalated before the grace period elapsed"
    assert wait_until(lambda: not is_pid_alive(pid))


def test_child_of_child_is_also_stopped():
    """Signalling the group, not the PID, is what stops forked helpers.

    v2 signalled a single PID and left strays behind — including, in the ssh -f
    case, the process actually carrying the tunnel.

    Kept to POSIX sh: an earlier version used ``exec -a`` to give the grandchild
    a recognisable name, which is a bash builtin. macOS's /bin/sh accepts it and
    Ubuntu's dash does not, so the grandchild died instantly in CI and the test
    failed for a reason that had nothing to do with process groups.
    """
    script = "sleep 300 & echo $!; wait"
    proc = SupervisedProcess(argv=["/bin/sh", "-c", script])
    proc.start()

    assert wait_until(lambda: proc.stdout_tail(), timeout=5)
    grandchild_pid = int(proc.stdout_tail()[0].strip())
    assert is_pid_alive(grandchild_pid)

    proc.stop(grace_seconds=3)

    assert wait_until(lambda: not is_pid_alive(grandchild_pid), timeout=5)


def test_child_does_not_share_the_parent_process_group():
    """start_new_session isolates the child so a Ctrl-C to the daemon's terminal
    does not tear down every live tunnel."""
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "sleep 300"])
    pid = proc.start()
    try:
        assert os.getpgid(pid) != os.getpgid(os.getpid())
        assert os.getpgid(pid) == pid
    finally:
        proc.stop(grace_seconds=2)


def test_chatty_process_does_not_deadlock():
    """A full pipe buffer must not stall the child.

    Without draining, a noisy process blocks on write forever, which is
    indistinguishable from a healthy long-running tunnel.
    """
    script = "for i in $(seq 1 20000); do echo 'x line of output padding padding padding'; done"
    proc = SupervisedProcess(argv=["/bin/sh", "-c", script], log_lines=50)
    proc.start()

    assert wait_until(lambda: proc.poll() is not None, timeout=30), "process stalled on a full pipe"
    assert proc.poll().returncode == 0
    # Ring buffer keeps memory bounded regardless of how much was produced.
    assert len(proc.stdout_tail()) <= 50


def test_stop_is_never_blocked_by_a_full_pipe():
    script = "while true; do echo 'noise noise noise noise noise'; done"
    proc = SupervisedProcess(argv=["/bin/sh", "-c", script], log_lines=20)
    pid = proc.start()
    proc.stop(grace_seconds=3)
    assert wait_until(lambda: not is_pid_alive(pid))


# ── Environment isolation ───────────────────────────────────────────────


def test_child_environment_is_scrubbed(monkeypatch):
    """A child must not inherit unrelated secrets from the daemon."""
    monkeypatch.setenv("MUDALE_TEST_SECRET", "should-not-be-inherited")
    proc = SupervisedProcess(
        argv=[
            sys.executable,
            "-c",
            "import os; print(os.environ.get('MUDALE_TEST_SECRET', 'ABSENT'))",
        ]
    )
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    assert "ABSENT" in proc.poll().stdout_tail


def test_adapter_env_is_merged_over_the_base():
    proc = SupervisedProcess(
        argv=[sys.executable, "-c", "import os; print(os.environ.get('ADAPTER_VAR', 'MISSING'))"],
        env={"ADAPTER_VAR": "present"},
    )
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    assert "present" in proc.poll().stdout_tail


def test_stdin_is_closed():
    """Nothing the engine runs may wait on input from a terminal it does not have."""
    proc = SupervisedProcess(argv=["/bin/sh", "-c", "cat; echo done"])
    proc.start()
    assert wait_until(lambda: proc.poll() is not None, timeout=5), "process waited on stdin"


# ── Output callback ─────────────────────────────────────────────────────


def test_output_callback_receives_lines():
    seen: list[tuple[str, str]] = []
    proc = SupervisedProcess(
        argv=["/bin/sh", "-c", "echo alpha; echo beta >&2"],
        on_output=lambda stream, line: seen.append((stream, line)),
    )
    proc.start()
    assert wait_until(lambda: len(seen) >= 2)
    assert ("stdout", "alpha") in seen
    assert ("stderr", "beta") in seen


def test_failing_output_callback_does_not_kill_the_process():
    def explode(stream, line):
        raise RuntimeError("callback is broken")

    proc = SupervisedProcess(argv=["/bin/sh", "-c", "echo hello; exit 0"], on_output=explode)
    proc.start()
    assert wait_until(lambda: proc.poll() is not None)
    assert proc.poll().returncode == 0


# ── is_pid_alive ────────────────────────────────────────────────────────


def test_is_pid_alive_for_self_and_impossible_pids():
    assert is_pid_alive(os.getpid())
    assert not is_pid_alive(0)
    assert not is_pid_alive(-1)
