"""Real-signal tests for ``RunningProcess.kill_now`` (SCU-1340).

These exercise the OS-level mechanism the SCU-1340 fix relies on: signalling a
running process's *group* directly from the caller's thread (``os.killpg``),
escalating SIGTERM → SIGKILL, so that a SIGTERM-ignoring agent CLI and the
foreground subprocesses it spawned are all reaped. This is the half of the fix
that the (mock-based) ``ClaudeProcessManager`` unit test cannot prove because it
depends on real signals and process-group semantics.
"""

import os
import shlex
import signal
import time
from pathlib import Path
from queue import Queue
from threading import Event

from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.processes.local_process import run_background


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_pid_file(path: Path, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text().strip()
            if text:
                return int(text)
        time.sleep(0.02)
    raise FileNotFoundError(f"PID file {path} not created within {timeout}s")


def _wait_until_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return True
        time.sleep(0.02)
    return False


def test_kill_now_escalates_sigterm_then_sigkill_across_the_process_group(tmp_path: Path) -> None:
    """A SIGTERM-ignoring process group survives ``kill_now(SIGTERM)`` but is
    fully reaped — leader AND a SIGTERM-ignoring descendant — by
    ``kill_now(SIGKILL)``.

    This mirrors the SCU-1340 scenario: the agent CLI (and a child it spawned)
    trap SIGTERM, so Stop must escalate to SIGKILL on the whole group, issued
    directly (``killpg``) rather than via the worker thread's shutdown path.
    """
    leader_pid_path = tmp_path / "scu1340_leader.pid"
    child_pid_path = tmp_path / "scu1340_child.pid"
    leader_pid: int | None = None
    child_pid: int | None = None
    try:
        # Inner (child) shell: ignore SIGTERM, record its PID, loop forever.
        inner = f"trap '' TERM; echo $$ > {child_pid_path}; while true; do sleep 1; done"
        # Outer (leader) shell: ignore SIGTERM, record its PID, spawn the child
        # in the SAME process group (no setsid), loop forever.
        script = (
            f"trap '' TERM; echo $$ > {leader_pid_path}; sh -c {shlex.quote(inner)} & while true; do sleep 1; done"
        )

        proc = run_background(["sh", "-c", script], isolate_process_group=True)

        leader_pid = _wait_for_pid_file(leader_pid_path)
        child_pid = _wait_for_pid_file(child_pid_path)
        assert _is_alive(leader_pid), "leader should be alive after recording its PID"
        assert _is_alive(child_pid), "child should be alive after recording its PID"

        # SIGTERM is ignored by both — they must still be alive a moment later.
        # This is the bug: SIGTERM alone never stops them.
        proc.kill_now(signal.SIGTERM)
        time.sleep(1.0)
        assert _is_alive(leader_pid), "leader ignored SIGTERM but was killed by it anyway"
        assert _is_alive(child_pid), "child ignored SIGTERM but was killed by it anyway"

        # SIGKILL on the process group reaps everything, descendants included.
        proc.kill_now(signal.SIGKILL)
        assert _wait_until_dead(leader_pid), "leader survived SIGKILL on its process group"
        assert _wait_until_dead(child_pid), "SIGTERM-ignoring child survived SIGKILL on the process group"
    finally:
        for pid in (child_pid, leader_pid):
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        leader_pid_path.unlink(missing_ok=True)
        child_pid_path.unlink(missing_ok=True)


def test_kill_now_is_a_noop_before_the_process_spawns() -> None:
    """``kill_now`` must not raise if the process never spawned (``_popen``
    is None) — the interrupt path calls it defensively."""
    # A RunningProcess that was constructed but never started has no Popen.
    proc = RunningProcess(command=["true"], output_queue=Queue(), shutdown_event=Event())
    proc.kill_now(signal.SIGKILL)  # must not raise
