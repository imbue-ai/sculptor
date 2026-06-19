"""Real Claude integration tests: background tasks.

Verifies that background tasks (via Agent tool and Bash tool) behave correctly
with the stdin protocol — specifically that the agent turn stays open until
background tasks complete, and that interrupts work during background tasks.
"""

import time

import pytest
from playwright.sync_api import expect

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_claude.helpers import _get_assistant_messages
from tests.integration.real_claude.helpers import assert_any_message_contains
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import get_transcript_background_tasks
from tests.integration.real_claude.helpers import get_transcript_path
from tests.integration.real_claude.helpers import interrupt_agent
from tests.integration.real_claude.helpers import read_transcript
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait
from tests.integration.real_claude.helpers import wait_for_any_assistant_text
from tests.integration.real_claude.helpers import wait_for_thinking_indicator_to_settle

# The sleep duration for background tasks. Must be long enough that the
# process shutdown (close_stdin + 5s wait + SIGTERM) would kill the task
# before it completes if the bug is present.
_BG_SLEEP_SECONDS = 30

# If the first turn completes faster than this, the command ran in the
# background (not foreground). If it takes ~_BG_SLEEP_SECONDS, the agent
# ran it as a blocking foreground call and the test isn't exercising the
# background task path.
_MAX_FIRST_TURN_SECONDS = 15

# After the first turn completes, the process must stay alive at least this
# long for the background task to finish. With the bug (close_stdin + 5s +
# SIGTERM), the process dies in ~5-10s. Without the bug, it stays alive
# for the remaining ~25s of sleep 30.
_MIN_BG_WAIT_SECONDS = 15


@real_claude
@pytest.mark.timeout(300)
def test_agent_background_task_completes(sculptor_instance_: SculptorInstance) -> None:
    """Agent tool with run_in_background waits for the task to finish.

    The CLI holds the turn open (no result message) until all background Agent
    tasks have completed. The ThinkingIndicator should remain visible for the
    full duration of the background task.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Use the Agent tool to run `sleep 15` in a Bash command. Set run_in_background to true. After launching it, say 'AGENT-BG-LAUNCHED-71024' and wait for it to complete. When the background task finishes, say 'AGENT-BG-DONE-71024'."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the turn to finish. The default Playwright timeout (30s) is too
    # tight for a 15s background sleep + agent overhead, so use the explicit
    # real-Claude response timeout.  Use the flicker-tolerant settle helper
    # because in alpha the StatusPill unmounts briefly between turns (when
    # the first request finalizes before the bg-task-notification turn
    # arrives) — plain not_to_be_visible would return at 0s in that window.
    # Agent-tool turns spawn a subagent which inflates wall-clock time well
    # past the 120s default — empirically ~120-140s — so go wider.
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=240_000)

    # The key assertion: the agent reported the task finished, meaning the
    # turn stayed open long enough for the background agent to complete.
    # Use assert_any (not assert_last) because Claude may split its response
    # across multiple message blocks.
    assert_any_message_contains(chat_panel, "AGENT-BG-LAUNCHED-71024")
    assert_any_message_contains(chat_panel, "AGENT-BG-DONE-71024")
    assert_no_errors(chat_panel)

    # TRANSCRIPT DIAGNOSTICS: verify task_started/task_notification pairing.
    # If task_started events outnumber task_notification events, the CLI
    # failed to emit a completion notification — confirming the deadlock bug.
    transcript_path = get_transcript_path(sculptor_instance_, task_page)
    transcript = read_transcript(transcript_path)
    started, notifications = get_transcript_background_tasks(transcript)
    assert len(notifications) >= len(started), (
        f"Background task notification mismatch: {len(started)} started but only "
        + f"{len(notifications)} notifications received. "
        + f"Started: {started}, Notifications: {notifications}"
    )


@real_claude
@pytest.mark.timeout(300)
def test_bash_background_task_completes(sculptor_instance_: SculptorInstance) -> None:
    """Bash tool with run_in_background waits for the task to finish.

    When the Bash tool runs a command in the background, the CLI emits a result
    message immediately (the main turn ends). However, the background task
    continues running inside the CLI process. Sculptor must keep the process
    alive until all background task notifications arrive.

    This test uses timing: with the bug, the process is killed ~10s after
    launch (close_stdin + 5s wait + SIGTERM). Without the bug, the process
    stays alive for the full sleep duration (~30s). We assert the turn stays
    open for at least 20s after the first turn completes.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            f"Do a Bash tool call that runs `sleep {_BG_SLEEP_SECONDS}` with run_in_background set to true, and end your turn right away. Do NOT wait for the sleep to finish — just launch it in the background and immediately say 'BASH-BG-LAUNCHED-83920'. Nothing else."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the agent to say it launched the background task.
    # Track timing: if this takes ~_BG_SLEEP_SECONDS, the command ran in
    # the foreground and the test is not exercising the background path.
    start = time.monotonic()
    assert_any_message_contains(chat_panel, "BASH-BG-LAUNCHED-83920")
    first_turn_elapsed = time.monotonic() - start

    assert first_turn_elapsed < _MAX_FIRST_TURN_SECONDS, (
        f"First turn took {first_turn_elapsed:.1f}s — the agent likely ran sleep {_BG_SLEEP_SECONDS} in the foreground instead of backgrounding it. Expected < {_MAX_FIRST_TURN_SECONDS}s."
    )

    # Now measure how long until the ThinkingIndicator disappears.
    # With the bug: process is killed after close_stdin + 5s + SIGTERM ≈ 5-10s
    # Without the bug: process stays alive for the remaining ~25s of sleep 30.
    # Use the settle helper so the mid-turn StatusPill flicker (alpha view
    # unmounts the pill briefly when the first request finalizes before the
    # bg-task-notification turn arrives) doesn't satisfy the wait at 0s.
    wait_start = time.monotonic()
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=RESPONSE_TIMEOUT_MS)
    wait_elapsed = time.monotonic() - wait_start

    # The background task is sleep 30. The first turn took <15s. The remaining
    # sleep should keep the process alive for at least 15s more. With the bug,
    # the process dies in ~5-10s after the first turn.
    assert wait_elapsed >= _MIN_BG_WAIT_SECONDS, (
        f"Turn ended {wait_elapsed:.1f}s after first turn — background task was likely killed by process shutdown. Expected the process to stay alive for at least {_MIN_BG_WAIT_SECONDS}s while the background sleep completes."
    )
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_bash_background_task_not_killed(sculptor_instance_: SculptorInstance) -> None:
    """Bash background task completes within the same turn.

    Regression test for the specific bug where closing stdin and terminating
    the CLI process after the result message would kill in-flight background
    Bash tasks. This test tells the agent to say a completion marker ONLY
    after the background task notification arrives. With the bug, the process
    is killed before the notification, so the marker never appears.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            f"Do a Bash tool call that runs `sleep {_BG_SLEEP_SECONDS}` with run_in_background set to true, and end your turn right away. Do NOT wait for the sleep to finish — just launch it in the background and immediately say 'LAUNCHED-49201'. When you later receive the background task notification that the sleep completed, say 'BG-NOTIFICATION-RECEIVED-49201'."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the agent to report launch. Verify it was actually backgrounded.
    start = time.monotonic()
    assert_any_message_contains(chat_panel, "LAUNCHED-49201")
    first_turn_elapsed = time.monotonic() - start

    assert first_turn_elapsed < _MAX_FIRST_TURN_SECONDS, (
        f"First turn took {first_turn_elapsed:.1f}s — agent ran sleep in foreground. Expected < {_MAX_FIRST_TURN_SECONDS}s."
    )

    # Now measure how long until all output settles. With the bug, the process
    # is killed after close_stdin + 5s + SIGTERM (~5-10s). Without the bug,
    # the process stays alive for ~25s more (remaining sleep 30 time).
    # Settle helper filters the alpha mid-turn pill flicker; see
    # test_agent_background_task_completes for the rationale.
    wait_start = time.monotonic()
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=RESPONSE_TIMEOUT_MS)
    wait_elapsed = time.monotonic() - wait_start

    assert wait_elapsed >= _MIN_BG_WAIT_SECONDS, (
        f"Turn ended {wait_elapsed:.1f}s after first turn — background task was likely killed by process shutdown. Expected the process to stay alive for at least {_MIN_BG_WAIT_SECONDS}s while the background sleep completes."
    )

    # Also verify the agent received the completion notification
    assert_any_message_contains(chat_panel, "BG-NOTIFICATION-RECEIVED-49201")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_thinking_indicator_visible_during_background_bash(sculptor_instance_: SculptorInstance) -> None:
    """ThinkingIndicator stays visible while a background Bash task runs.

    After the agent launches a background Bash task and ends its main turn,
    the UI should continue showing the ThinkingIndicator until the background
    task completes and the agent responds to the notification.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            f"I need to test background task behavior. Do a Bash tool call that runs `sleep {_BG_SLEEP_SECONDS}` with run_in_background set to true, and end your turn right away. Do NOT wait for it to finish — just launch it and immediately say 'BG-RUNNING-60134'. Nothing else."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the agent to say it launched the background task
    start = time.monotonic()
    messages = chat_panel.get_messages()
    expect(messages.last).to_contain_text("BG-RUNNING-60134", timeout=RESPONSE_TIMEOUT_MS)
    first_turn_elapsed = time.monotonic() - start

    assert first_turn_elapsed < _MAX_FIRST_TURN_SECONDS, (
        f"First turn took {first_turn_elapsed:.1f}s — agent ran sleep in foreground. Expected < {_MAX_FIRST_TURN_SECONDS}s."
    )

    # The ThinkingIndicator should STILL be visible because the background
    # task is running (sleep _BG_SLEEP_SECONDS). The first turn ended quickly
    # (~5s) but the background task won't finish for another ~25s.
    thinking = chat_panel.get_thinking_indicator()
    expect(thinking).to_be_visible()

    # With the bug, the ThinkingIndicator disappears after ~10s (close_stdin
    # + 5s wait + SIGTERM kills the process). Without the bug, it should stay
    # visible for close to the full sleep duration. Wait 20s and verify the
    # indicator is STILL visible — proving the turn hasn't ended prematurely.
    chat_panel._page.wait_for_timeout(20_000)
    expect(thinking).to_be_visible()

    # Now wait for the turn to actually finish (background task completes)
    expect(thinking).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_during_background_agent_task(sculptor_instance_: SculptorInstance) -> None:
    """Interrupt works cleanly during a background Agent task.

    When the agent has launched a background task via the Agent tool and is
    waiting for it to complete, the user should be able to interrupt. The
    agent should recover and respond to follow-up messages.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Use the Agent tool to run `sleep 60` in a Bash command. Set run_in_background to true. After launching it, write a 2000-word essay about the ocean. Start with OCEAN-ESSAY-START:"
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for some output then interrupt
    wait_for_any_assistant_text(chat_panel)
    chat_panel._page.wait_for_timeout(3000)
    interrupt_agent(chat_panel)

    # Verify recovery
    send_and_wait(chat_panel, "Reply with exactly: BG-AGENT-INTERRUPT-RECOVERED-52018")
    assert_last_message_contains(chat_panel, "BG-AGENT-INTERRUPT-RECOVERED-52018")


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_during_background_bash_task(sculptor_instance_: SculptorInstance) -> None:
    """Interrupt works cleanly during a background Bash task.

    The user interrupts while the background Bash command is still running.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "I need you to do two things in this EXACT order:\n"
        + "1. Use the Bash tool to run `sleep 60` with run_in_background set to true.\n"
        + "2. IMMEDIATELY after launching it (do NOT wait for it to finish), write a very long, "
        + "detailed, 2000-word essay about the history of mountain climbing. Number each "
        + "paragraph. Start the essay text with the marker MOUNTAIN-ESSAY-START:",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the agent to start writing the essay, then interrupt.
    # If the agent finishes its turn before starting the essay (e.g., it just
    # launched bash and stopped), the thinking indicator will disappear. In that
    # case the test isn't exercising the interrupt path, so we still verify recovery.
    thinking = chat_panel.get_thinking_indicator()
    expect(thinking).to_be_visible(timeout=30_000)
    # Give the agent time to launch bash and start writing
    chat_panel._page.wait_for_timeout(5000)

    # Only interrupt if the agent is still active
    if thinking.is_visible():
        interrupt_agent(chat_panel)

    # Verify recovery (works whether we interrupted or agent finished naturally)
    send_and_wait(chat_panel, "Reply with exactly: BG-BASH-INTERRUPT-RECOVERED-38201")
    assert_last_message_contains(chat_panel, "BG-BASH-INTERRUPT-RECOVERED-38201")


@real_claude
@pytest.mark.timeout(120)
def test_post_notification_message_delivered(sculptor_instance_: SculptorInstance) -> None:
    """Post-notification assistant message appears in the chat UI.

    Regression test for a bug where the output processor loop exits immediately
    after clearing ``_pending_background_tasks``, before reading the
    post-notification turn (init → assistant → result).  The transcript file
    contains the response, but the UI never displays it.

    Uses a short sleep (5s) since the bug is not timing-dependent — the loop
    exits as soon as the TaskNotificationMessage is processed, regardless of
    how long the background task took.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Do a Bash tool call that runs `sleep 5` with run_in_background "
            + "set to true, and end your turn right away. Do NOT wait for the "
            + "sleep to finish — just launch it in the background and immediately "
            + "say 'LAUNCHED-82047'. When you later receive the background task "
            + "notification that the sleep completed, say 'POSTNOTIFY-82047'."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the first turn: agent launches background task and says LAUNCHED.
    assert_any_message_contains(chat_panel, "LAUNCHED-82047")

    # Wait for everything to settle (thinking indicator disappears).
    # Settle helper filters the alpha mid-turn pill flicker that happens
    # between the LAUNCHED turn and the bg-task-notification turn.
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=RESPONSE_TIMEOUT_MS)

    # The critical assertion: the post-notification response must be visible.
    # With the bug, the output loop exits after the TaskNotificationMessage
    # clears _pending_background_tasks, so this message is never delivered
    # to the UI even though it exists in the transcript.
    #
    # Check assistant messages only — the user message contains the marker as
    # quoted instruction text which would false-positive on get_messages().
    assistant_msgs = _get_assistant_messages(chat_panel)
    expect(assistant_msgs.filter(has_text="POSTNOTIFY-82047").first).to_be_visible()
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_follow_up_after_background_task(sculptor_instance_: SculptorInstance) -> None:
    """Agent responds correctly to follow-up after background task completes.

    After a background task finishes and the turn ends, verify the agent can
    handle a follow-up message and still has conversation context.
    """
    # Use wait_for_finish=False because the default 30s thinking-indicator
    # timeout inside start_task_and_wait_for_ready is too short for a turn
    # that includes a 10s background task + the post-notification reply.
    # We do our own settle below with the real-Claude RESPONSE_TIMEOUT_MS.
    #
    # The prompt uses Bash with run_in_background directly (not Agent +
    # subagent), because the Agent tool is non-deterministic about how it
    # interprets "run sleep in background" and we saw turns that never
    # settled within 240s of wall clock. The follow-up message is what we
    # actually care about here — verifying conversation context survives a
    # bg-task notification turn — and Bash exercises the same code path.
    prompt = "Remember this code: ANCHOR-DELTA-77301. Then use the Bash tool with run_in_background=true to run: sleep 10. Immediately say 'BG-LAUNCHED-77301' and end your turn. When you receive the background task completion notification, say exactly: TASK-FINISHED-77301."  # noqa: E501
    task_page = create_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=False)
    chat_panel = task_page.get_chat_panel()
    # 240s headroom: the bg-task notification cycle empirically takes
    # 120-140s with this prompt under model variance.
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=240_000)
    assert_any_message_contains(chat_panel, "TASK-FINISHED-77301")

    # Follow-up: verify context is preserved
    send_and_wait(
        chat_panel,
        "What code did I ask you to remember? Reply starting with RECALL-DELTA:",
    )
    assert_last_message_contains(chat_panel, "ANCHOR-DELTA-77301")


@real_claude
@pytest.mark.timeout(300)
def test_background_subagent_pill_completes(sculptor_instance_: SculptorInstance) -> None:
    """SCU-1151: the background subagent pill must stop ticking on completion.

    Real Claude routes the subagent's content (its text, tool calls, final
    reply) through a separate CLI process — only a task_notification with
    {tool_use_id, status, summary, usage.duration_ms, output_file} is
    streamed to the parent.  No child messages with parent_tool_use_id ever
    reach the parent's chatMessages.

    Without the message_conversion synthesis fix, buildSubagentMetadataMap's
    second pass finds no child message → metadata.responseText stays
    undefined → AlphaSubagentPill keeps isThinking=true → the displayed
    duration keeps ticking up forever, even after the main agent has
    received the notification and replied "Subagent done."

    Repro is the minimum-cost variant the SCU-1151 reporter used: launch a
    background Agent doing `ls; sleep 2` and a one-line reply.
    """
    prompt = (
        "Launch a background subagent (Agent tool with run_in_background true,"
        + " subagent_type general-purpose) and give it this prompt verbatim:"
        + " 'Run exactly one Bash call: ls; sleep 2. After it returns, reply"
        + " with a single short line: Done — 1 ls/sleep complete.' After"
        + " launching the subagent, immediately say 'BG-LAUNCHED-39014' and"
        + " end your turn. When you receive the completion notification, say"
        + " exactly: BG-COMPLETE-39014."
    )
    task_page = create_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=False)
    chat_panel = task_page.get_chat_panel()

    # Wait for the launch turn so we know the Agent tool_use is in the chat.
    assert_any_message_contains(chat_panel, "BG-LAUNCHED-39014")

    # Wait through the bg-task-notification cycle. 240s headroom matches
    # other real-Claude bg-task tests in this file.
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=240_000)
    assert_any_message_contains(chat_panel, "BG-COMPLETE-39014")

    # The subagent pill must be rendered with the prompt visible.
    page = chat_panel._page
    pill = chat_panel.get_subagent_pills()
    expect(pill).to_have_count(1)
    expect(pill).to_contain_text("ls; sleep 2")

    # The critical SCU-1151 assertion: the pill must STOP ticking once the
    # notification arrives. Sample the pill text twice with a delay between
    # and assert the displayed timer doesn't change. With the bug, the text
    # changes (timer advancing by ~3s in this window).
    text_t1 = pill.inner_text()
    page.wait_for_timeout(3_000)
    text_t2 = pill.inner_text()
    assert text_t1 == text_t2, (
        "Background subagent pill kept ticking after the turn finished:\n"
        + f"  t1: {text_t1!r}\n  t2: {text_t2!r}\n"
        + "Expected the timer to freeze once task_notification arrived."
    )
    assert_no_errors(chat_panel)
