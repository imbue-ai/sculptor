"""Real Claude verification for SCU-211.

The FakeClaude test in ``sculptor/tests/integration/frontend/test_stop_kills_foreground_processes.py``
proves that Sculptor's process-group isolation kills children of a hung
agent CLI. That guarantee only holds end-to-end if the real Claude CLI
spawns its Bash tool's shell into the agent's own process group (no
``setsid``). This test verifies that assumption against the actual Claude
binary end-to-end: ask real Claude to run a long-running Bash command,
record the shell's PID, click Stop, and confirm the OS process is dead.

If Claude ever ships a change that puts each Bash tool invocation in its
own session/process group, this test will start failing and we'll know
the fix needs to be re-evaluated (e.g. switching to a tree-walking
shutdown strategy).
"""

import os
import signal
import tempfile
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import interrupt_agent
from tests.integration.real_claude.helpers import real_claude


def _is_process_alive(pid: int) -> bool:
    """Check whether a process is still running (signal 0 probe)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_process(pid: int) -> None:
    """Best-effort kill of a leaked process."""
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


@real_claude
@pytest.mark.timeout(300)
def test_stop_kills_real_claude_bash_subprocess(sculptor_instance_: SculptorInstance) -> None:
    """Real Claude variant of the SCU-211 fix verification.

    Asks Claude to run ``echo $$ > <pid_file> && exec sleep 300`` via the
    Bash tool. The ``exec`` replaces the shell with ``sleep`` so the recorded
    PID belongs to the long-running process Stop must kill. After clicking
    Stop the PID must be dead within ~20s (well past the 5s stdin-interrupt
    grace + 5s SIGTERM grace that Sculptor uses).
    """
    pid_path = Path(tempfile.mktemp(prefix="scu211_real_claude_", suffix=".pid"))
    leaked_pid: int | None = None

    try:
        prompt = (
            "Run a long-lived shell process so this automated test can verify that Stop kills it. "
            + "Call the Bash tool exactly once, with this exact command and nothing else:\n"
            + f"`echo $$ > {pid_path} && exec sleep 300`\n"
            + "This command is expected to run for a long time without returning — that is "
            + "intentional and correct for this test. Do not modify it, do not wrap it, do not add a "
            + "timeout, and do not add any commentary before or after the tool call."
        )
        task_page = create_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=False)
        chat_panel = task_page.get_chat_panel()

        # Wait for Claude to actually launch the bash command — i.e. for the
        # PID file to land on disk. Real Claude takes a few seconds to plan
        # the tool call before invoking it, so the deadline is generous.
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline and not pid_path.exists():
            time.sleep(0.5)
        assert pid_path.exists(), f"Real Claude never invoked the bash command (no PID file at {pid_path} within 60s)"

        pid_text = pid_path.read_text().strip()
        assert pid_text, f"PID file {pid_path} was created empty"
        leaked_pid = int(pid_text)
        assert _is_process_alive(leaked_pid), (
            f"Bash subprocess (PID {leaked_pid}) should be alive immediately after writing its PID"
        )

        # The thinking indicator should still be visible — Claude is blocked
        # waiting for the Bash tool to return.
        expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=10_000)

        interrupt_agent(chat_panel)

        # Confirm the subprocess is dead within 20s. Without process-group
        # isolation the PID survives indefinitely; with the fix it dies once
        # Sculptor's shutdown path lands (~ stdin interrupt grace, or worst
        # case SIGKILL via killpg).
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and _is_process_alive(leaked_pid):
            time.sleep(0.2)

        assert not _is_process_alive(leaked_pid), (
            f"Real Claude's Bash subprocess (PID {leaked_pid}) is still alive 20s after Stop. "
            + "Either Claude is spawning Bash tool subprocesses in their own session/process group "
            + "(in which case the SCU-211 process-group fix doesn't reach them) or Sculptor's "
            + "shutdown path itself regressed."
        )
    finally:
        if leaked_pid is not None:
            _kill_process(leaked_pid)
        pid_path.unlink(missing_ok=True)
