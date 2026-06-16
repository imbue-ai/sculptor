"""Real pi integration tests: background tasks and clean child shutdown.

Mirrors ``real_claude/test_background_tasks.py`` for pi's ``supports_background_tasks``
path: a real ``pi --mode rpc`` subprocess loads the pinned ``sculptor_background``
extension, the agent runs a long command in the background via the ``background``
tool, and Sculptor HOLDS the turn open (StatusPill "Waiting") until the task
reports completion out-of-band — then reconciles the completion into the
conversation.

A second test exercises the no-orphan guarantee on a MID-FLIGHT interrupt (the
case pi-core gives no extension hook for): Stop while the background command is
still running kills the detached child, leaving no orphan, via Sculptor's
in-environment SIGTERM of the child's process group.

Divergence note (REQ-TEST-1): pi surfaces the completion as a reconciled summary
block rather than a fresh agent turn reacting to a ``task_notification`` (pi
0.78.0's extension model makes the post-notification agent turn add
double-emit/race risk for marginal benefit — see the MR). So these tests assert
the completion SURFACES and the turn stays open for the task's duration, rather
than asserting the agent emits a marker after completion as the real_claude
tests do.
"""

from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import assert_no_errors
from tests.integration.real_pi.helpers import count_processes_matching
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import interrupt_agent
from tests.integration.real_pi.helpers import real_pi
from tests.integration.real_pi.helpers import wait_for_process_count

# The `background` tool spawns ``bash -c <command>`` detached; embedding a unique
# marker in the command lets us see the background child appear and confirm it is
# gone (killed, not orphaned) without matching any unrelated process.


@real_pi
@pytest.mark.timeout(600)
def test_pi_background_task_holds_turn_open_then_reconciles_completion(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A backgrounded command does not block the turn, the turn stays open
    (StatusPill "Waiting") while it runs, and its completion is reconciled."""
    marker = f"PI-BG-OUT-{uuid.uuid4().hex[:8]}"
    prompt = (
        "Use the `background` tool to run a command in the background. Pass this EXACT shell "
        + f"command to the tool's `command` parameter: echo {marker}; sleep 8 . "
        + "After launching it, immediately reply with exactly BG-LAUNCHED and end your turn. "
        + "Do NOT wait for the command to finish and do NOT run it yourself."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=False)
    chat_panel = task_page.get_chat_panel()
    page = sculptor_instance_.page

    # The turn is held open while the background command runs: the StatusPill
    # shows the background-wait state (the agent's own run already ended — it did
    # not block on the command).
    expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_have_attribute(
        "data-agent-state", "waiting_for_background", timeout=RESPONSE_TIMEOUT_MS
    )

    # The completion is reconciled into the conversation (the command's output is
    # surfaced in the completion summary), and the wait chrome clears.
    expect(chat_panel.get_assistant_messages().filter(has_text=marker).first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_have_count(0, timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_pi
@pytest.mark.timeout(600)
def test_pi_background_task_interrupt_leaves_no_orphan(sculptor_instance_: SculptorInstance) -> None:
    """Stopping a turn while a backgrounded command is still running kills the
    detached child — no orphan survives the mid-flight interrupt (Sculptor
    SIGTERMs the child's process group in the environment)."""
    # Identify the long-lived background child by a UNIQUE sleep duration rather
    # than an echo marker: `bash -c "echo X; sleep N"` exec-optimizes into
    # `sleep N` after the echo, so the surviving process's argv is just
    # `sleep N` — the unique N is what stays greppable for the whole run.
    unique_seconds = 100000 + int(uuid.uuid4().hex[:6], 16) % 800000
    sleep_token = f"sleep {unique_seconds}"
    matches_sleep = lambda cmdline: sleep_token in " ".join(cmdline)  # noqa: E731
    baseline = count_processes_matching(matches_sleep)

    # Launch a long-running background command in the FIRST turn — the same
    # single-prompt shape the hold-open test uses (most reliable tool-calling).
    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        "Use the `background` tool to run a command in the background. Pass this EXACT shell "
        + f"command to the tool's `command` parameter: {sleep_token} . "
        + "After launching it, immediately reply with exactly BG-LAUNCHED and end your turn. "
        + "Do NOT wait for it and do NOT run it yourself.",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait until the detached background child is actually running, then interrupt
    # the held-open turn while it runs.
    appeared = wait_for_process_count(matches_sleep, baseline + 1, at_least=True, timeout_s=120)
    assert appeared > baseline, "background child process never started"

    interrupt_agent(chat_panel)

    # The child's process group is torn down by Sculptor's in-environment kill.
    remaining = wait_for_process_count(matches_sleep, baseline, at_least=False, timeout_s=30)
    assert remaining <= baseline, f"orphan background child after Stop: {remaining} > {baseline}"
