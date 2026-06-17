"""Real pi integration tests: sub-agents (yield-early) and survival across Stop.

A real ``pi --mode rpc`` subprocess loads the pinned ``sculptor_subagent``
extension; the agent delegates work via the ``subagent`` tool. Under the
yield-early model the launching turn ENDS immediately — the user keeps chatting
while the children run — and each child's activity is surfaced out-of-band by
Sculptor's idle-drain as the nested ``AlphaSubagentPill`` (parent entry +
attributed child activity).

These exercise the two behaviours end-to-end against real pi:
- the launch turn yields, the main thread stays interactive while a child runs,
  and the child's activity is surfaced as the nested pill when it completes;
- a running sub-agent SURVIVES the user stopping a later turn (it is independent
  of the turn that launched it). No-orphan ON SHUTDOWN is covered by the unit
  tests (``agent_wrapper_test.test_shutdown_cancels_subagent_tasks`` plus the
  extension's ``session_shutdown`` handler).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import assert_no_errors
from tests.integration.real_pi.helpers import count_processes_matching
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import interrupt_agent
from tests.integration.real_pi.helpers import kill_processes_matching
from tests.integration.real_pi.helpers import real_pi
from tests.integration.real_pi.helpers import send_no_wait
from tests.integration.real_pi.helpers import wait_for_process_count
from tests.integration.real_pi.helpers import wait_for_streaming_text


def _is_child_pi(cmdline: Sequence[str]) -> bool:
    """A live child sub-agent process: ``pi --mode json -p --no-session``.

    The long-lived parent agent is ``--mode rpc``, so matching ``--mode json``
    isolates children. Used to assert a child started, survives a Stop, and is
    cleaned up.
    """
    return "--mode" in cmdline and "json" in cmdline and "pi" in " ".join(cmdline)


@real_pi
@pytest.mark.timeout(600)
def test_pi_subagent_yields_interactive_and_completes(sculptor_instance_: SculptorInstance) -> None:
    """The launch turn yields immediately, the main thread answers a message WHILE the
    sub-agent runs (no Stop), and the child's activity is surfaced out-of-band as the
    nested AlphaSubagentPill when it completes."""
    reply_marker = f"PI-REPLY-{uuid.uuid4().hex[:6]}"
    prompt = (
        "Use your subagent tool to delegate exactly one task to a single sub-agent. "
        + 'Pass this as the task: "Run the shell command: echo PI-SUBAGENT-CHILD-50231; sleep 8". '
        + "Delegate it via the subagent tool; do not run it yourself. "
        + "After launching it, immediately reply with exactly SA-LAUNCHED and end your turn. "
        + "Do NOT wait for the sub-agent to finish."
    )
    # wait_for_finish=True: the launching turn ENDS on its own (yield-early) — if the
    # agent wrongly held the turn open until the children finished this would time out.
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=True)
    chat_panel = task_page.get_chat_panel()

    # Interactive WHILE the sub-agent runs (its sleep is still going): a follow-up is
    # answered without any Stop.
    send_no_wait(chat_panel, f"Reply with exactly {reply_marker} and nothing else.")
    expect(chat_panel.get_assistant_messages().filter(has_text=reply_marker).first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )

    # The sub-agent's activity is surfaced out-of-band as the nested pill when it
    # completes (the gate no longer suppresses it for pi).
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    assert_no_errors(chat_panel)

    # No orphan child processes: the child exited when its command finished.
    remaining = wait_for_process_count(_is_child_pi, 0, at_least=False, timeout_s=30)
    assert remaining == 0, f"orphan child pi processes after clean run: {remaining}"


@real_pi
@pytest.mark.timeout(600)
def test_pi_subagent_survives_stop(sculptor_instance_: SculptorInstance) -> None:
    """Stopping a later turn must NOT kill a running sub-agent.

    A sub-agent is independent of the turn that launched it, so it survives an
    interrupt of any subsequent turn — it is torn down only on shutdown."""
    baseline = count_processes_matching(_is_child_pi)
    try:
        task_page = create_pi_workspace_and_send(
            sculptor_instance_,
            "Use your subagent tool to delegate exactly one task to a single sub-agent. "
            + 'Pass this as the task: "Run the shell command: sleep 240". '
            + "Delegate it via the subagent tool; do not run it yourself. "
            + "After launching it, immediately reply with exactly SA-LAUNCHED and end your turn. "
            + "Do NOT wait for it.",
            wait_for_finish=True,
        )
        chat_panel = task_page.get_chat_panel()

        # The detached sub-agent child is running.
        appeared = wait_for_process_count(_is_child_pi, baseline + 1, at_least=True, timeout_s=120)
        assert appeared > baseline, "sub-agent child process never started"

        # Send a follow-up, let it start streaming, then Stop it. The sub-agent must
        # keep running through the interrupt.
        send_no_wait(chat_panel, "Write a very long, detailed essay about the ocean. Start with OCEAN-ESSAY:")
        wait_for_streaming_text(chat_panel, "OCEAN-ESSAY")
        interrupt_agent(chat_panel)

        # The sub-agent SURVIVES the Stop (it is killed only on shutdown).
        still_running = wait_for_process_count(_is_child_pi, baseline, at_least=False, timeout_s=8)
        assert still_running > baseline, "sub-agent child was wrongly killed by Stop"
    finally:
        # Clean up the child we deliberately left running (the shared instance is
        # reused across tests on success, so don't leak it).
        kill_processes_matching(_is_child_pi)


@real_pi
@pytest.mark.timeout(600)
def test_pi_subagent_completion_wakes_the_agent(sculptor_instance_: SculptorInstance) -> None:
    """The sub-agent's completion wakes the calling agent (the extension's
    `sendUserMessage`), which reacts in a new turn — the auto-resume leg, end-to-end."""
    prompt = (
        "Use your subagent tool to delegate exactly one task to a single sub-agent. "
        + 'Pass this as the task: "Run the shell command: echo SA-CHILD-50240". '
        + "Delegate it via the subagent tool; do not run it yourself. "
        + "After launching it, reply with exactly SA-LAUNCHED and end your turn. "
        + "Later, when you are notified that the sub-agent has finished, reply with exactly "
        + "SA-RESUMED-50240 and nothing else."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=True)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_assistant_messages().filter(has_text="SA-LAUNCHED").first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    # The completion wakes the agent; it reacts in a new (auto-resume) turn.
    expect(chat_panel.get_assistant_messages().filter(has_text="SA-RESUMED-50240").first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    assert_no_errors(chat_panel)
