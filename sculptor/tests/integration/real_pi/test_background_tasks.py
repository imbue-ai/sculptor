"""Real pi integration tests: background tasks (yield-early) and clean shutdown.

A real ``pi --mode rpc`` subprocess loads the pinned ``sculptor_background``
extension; the agent runs a command in the background via the ``background`` tool.
Under the yield-early model the launching turn ENDS immediately — the user keeps
chatting while the task runs — and the task's completion is surfaced out-of-band
by Sculptor's idle-drain.

These exercise the two behaviours end-to-end against real pi:
- the launch turn yields, the main thread stays interactive while the task runs,
  and the completion is reconciled into the conversation when it finishes;
- a backgrounded task SURVIVES the user stopping a later turn (it is independent
  of the turn that launched it) — the regression Danver hit, where Stop wrongly
  killed the task. (No-orphan ON SHUTDOWN is covered by the unit tests:
  ``agent_wrapper_test.test_shutdown_cancels_background_tasks`` plus the
  extension's ``session_shutdown`` handler.)

Divergence note (REQ-TEST-1): pi surfaces the completion as a reconciled summary
block rather than a fresh agent turn reacting to a ``task_notification`` (pi
0.78.0's extension model makes the post-notification agent turn add
double-emit/race risk for marginal benefit — see the MR).
"""

from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import expect

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


@real_pi
@pytest.mark.timeout(600)
def test_pi_background_task_yields_interactive_and_completes(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The launch turn yields immediately, the main thread answers a message WHILE
    the task runs (no Stop), and the completion is reconciled when the task ends."""
    marker = f"PI-BG-OUT-{uuid.uuid4().hex[:8]}"
    reply_marker = f"PI-REPLY-{uuid.uuid4().hex[:6]}"
    prompt = (
        "Use the `background` tool to run a command in the background. Pass this EXACT shell "
        + f"command to the tool's `command` parameter: echo {marker}; sleep 8 . "
        + "After launching it, immediately reply with exactly BG-LAUNCHED and end your turn. "
        + "Do NOT wait for the command to finish and do NOT run it yourself."
    )
    # wait_for_finish=True: the launching turn ENDS on its own (yield-early) — if
    # the agent wrongly held the turn open this would time out.
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=True)
    chat_panel = task_page.get_chat_panel()

    # Yield-early, observably: the backgrounded `sleep` is still running now (the
    # launch turn ended while it runs) — a held-open turn would have finished it first.
    sleep_running = lambda cmdline: "sleep 8" in " ".join(cmdline)  # noqa: E731
    running = wait_for_process_count(sleep_running, 1, at_least=True, timeout_s=30)
    assert running >= 1, "backgrounded sleep not running after launch — yield-early not observable"

    # Interactive WHILE the task runs: a follow-up is answered without any Stop.
    send_no_wait(chat_panel, f"Reply with exactly {reply_marker} and nothing else.")
    expect(chat_panel.get_assistant_messages().filter(has_text=reply_marker).first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )

    # The completion is surfaced out-of-band (the command's output rides the
    # completion summary), reconciled into the conversation.
    expect(chat_panel.get_assistant_messages().filter(has_text=marker).first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    assert_no_errors(chat_panel)


@real_pi
@pytest.mark.timeout(600)
def test_pi_background_task_survives_stop(sculptor_instance_: SculptorInstance) -> None:
    """Stopping a later turn must NOT kill a running background task.

    Regression for the reported bug: a backgrounded `sleep` was killed when the
    user pressed Stop to interject. A backgrounded task is independent of the turn
    that launched it, so it survives an interrupt of any subsequent turn."""
    # A unique sleep duration identifies the long-lived child: `bash -c "sleep N"`
    # exec-optimizes into `sleep N`, so the surviving argv is just `sleep N`. Kept
    # moderate so a missed cleanup self-resolves quickly.
    unique_seconds = 200 + int(uuid.uuid4().hex[:4], 16) % 100  # 200–299s
    sleep_token = f"sleep {unique_seconds}"
    matches_sleep = lambda cmdline: sleep_token in " ".join(cmdline)  # noqa: E731
    baseline = count_processes_matching(matches_sleep)

    try:
        task_page = create_pi_workspace_and_send(
            sculptor_instance_,
            "Use the `background` tool to run a command in the background. Pass this EXACT shell "
            + f"command to the tool's `command` parameter: {sleep_token} . "
            + "After launching it, immediately reply with exactly BG-LAUNCHED and end your turn. "
            + "Do NOT wait for it and do NOT run it yourself.",
            wait_for_finish=True,
        )
        chat_panel = task_page.get_chat_panel()

        # The detached background child is running.
        appeared = wait_for_process_count(matches_sleep, baseline + 1, at_least=True, timeout_s=120)
        assert appeared > baseline, "background child process never started"

        # Send a follow-up, let it start streaming, then Stop it. The background
        # task must keep running through the interrupt.
        send_no_wait(chat_panel, "Write a very long, detailed essay about the ocean. Start with OCEAN-ESSAY:")
        wait_for_streaming_text(chat_panel, "OCEAN-ESSAY")
        interrupt_agent(chat_panel)

        # The background task SURVIVES the Stop (the bug: it used to be killed).
        # Sample for a few seconds; the count must stay above baseline.
        still_running = wait_for_process_count(matches_sleep, baseline, at_least=False, timeout_s=8)
        assert still_running > baseline, "background task was wrongly killed by Stop"
    finally:
        # Clean up the task we deliberately left running (the shared instance is
        # reused across tests on success, so don't leak it).
        kill_processes_matching(matches_sleep)


@real_pi
@pytest.mark.timeout(600)
def test_pi_background_task_completion_wakes_the_agent(sculptor_instance_: SculptorInstance) -> None:
    """The background task's completion wakes the calling agent (the extension's
    `sendUserMessage`), which reacts in a new turn — the auto-resume leg, end-to-end."""
    prompt = (
        "Use the `background` tool to run a command in the background. Pass this EXACT shell "
        + "command to the tool's `command` parameter: echo BG-CHILD-50241 . "
        + "After launching it, reply with exactly BG-LAUNCHED and end your turn. Do NOT wait for it. "
        + "Later, when you are notified that the background task has finished, reply with exactly "
        + "BG-RESUMED-50241 and nothing else."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=True)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_assistant_messages().filter(has_text="BG-LAUNCHED").first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    # The completion wakes the agent; it reacts in a new (auto-resume) turn.
    expect(chat_panel.get_assistant_messages().filter(has_text="BG-RESUMED-50241").first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    assert_no_errors(chat_panel)
