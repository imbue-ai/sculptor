"""Regression tests for "agent auto-replays prompt after restart" bugs.

When Sculptor restarts after the agent was in certain mid-turn states, the
user's prompt would silently get re-delivered to Claude on the next agent
run — making the agent appear to auto-start working on a prompt the user did
not just send. These tests pin the desired behavior end-to-end: after a
restart, the agent must NOT re-process a prompt the previous run already
delivered.

The replay scenarios covered here:

- ``test_chat_does_not_replay_after_shutdown_mid_turn``
  (Sculptor SIGTERM'd while Claude is still processing the chat prompt).
- ``test_chat_does_not_replay_after_shutdown_during_auq_wait``
  (Sculptor SIGTERM'd while the agent is waiting on an unanswered AUQ —
  ``user_input_message_being_processed`` is ``None`` in that state, so
  the mid-turn fix originally missed this path).

Other replay paths (orphaned answers, interrupted completions, derived-cursor
edge shapes) require triggers that ``SculptorInstanceFactory`` cannot
reproduce — SIGKILL at a precise point, or shutdown timed inside a
millisecond-scale window. Those are covered by backend unit tests in
``sculptor/sculptor/tasks/handlers/run_agent/v1_test.py``.

The mid-turn test uses ``fake_claude:sleep`` for a deterministic long-running
turn, so any replay would keep the agent in ``RUNNING`` for at least 120
seconds; it asserts the post-restart status reaches ``READY`` within a
generous timeout — only true if the restart scan (``scan_message_history``)
derives the killed prompt as settled (no partial output, nothing to resume)
and dedup therefore drops it so the loop has nothing to dispatch. The AUQ
test parks the agent on an unanswered question instead: that turn survives
the restart and pins the status at ``WAITING`` either way, so it
discriminates a replay by the AUQ tool block count — a replayed chat would
re-emit the question as a second tool block.

Note on user-clicked Stop: the Stop button does NOT trigger this bug
class, because Claude's clean exit on a stdin interrupt control_request
flows through the wrapper's success branch (``RequestSuccessAgentMessage``
with ``interrupted=True``), which the restart scan treats as a settled
turn. The bugs above only fire on the SIGTERM path, where the wrapper's
exception handler emits ``RequestStoppedAgentMessage``.
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.ask_user_question import get_ask_user_question_tool_blocks
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_SECONDS_MS = 1000

# An idle (READY) agent panel tab settles to a read/unread status dot once the
# user is viewing the workspace — the section shell exposes lifecycle as
# ``data-dot-status`` (the getAgentDotStatus vocabulary), not the raw TaskStatus.
# A replayed prompt would instead keep the dot at "running" for the whole sleep.
_IDLE_DOT_STATUS = re.compile(r"^(read|unread)$")

# Visibility gate for the post-restart page — generous because the Phase-2
# backend is restoring a previously-running task and CI can be slow.
_RESTART_VISIBILITY_TIMEOUT_MS = 60 * _SECONDS_MS

# The fake-claude sleep duration. Long enough that any replay would keep the
# agent in RUNNING for the entire ``_SETTLE_TIMEOUT_MS`` window below.
_SLEEP_PROMPT = 'fake_claude:sleep `{"seconds": 120}`'

# Window we give the post-restart task to settle into ``READY``. Has to be
# larger than the BUILDING phase (env acquisition + history walk + title
# prediction, ~5–15s on slow CI) but smaller than the 120s sleep so a
# replay can be distinguished from a slow build.
_SETTLE_TIMEOUT_MS = 60 * _SECONDS_MS

# Before tearing down the first instance, wait this long for the backend to
# observe the in-flight state we care about (RUNNING for the sleep path,
# AUQ-emitted for the AUQ path).
_INFLIGHT_OBSERVATION_TIMEOUT_MS = 30 * _SECONDS_MS

_AUQ_PROMPT = 'fake_claude:ask_user_question `{"questions": [{"question": "Pick a color", "header": "Color", "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": "cool"}], "multiSelect": false}]}`'  # noqa: E501


def _open_workspace_after_restart(page: Page) -> None:
    """Click the persisted workspace's sidebar row on a fresh Sculptor instance."""
    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    expect(workspace_row).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    workspace_row.click()


def _agent_tab(page: Page) -> Locator:
    return PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs().first


@user_story("not have my interrupted prompt silently re-run after Sculptor restarts")
def test_chat_does_not_replay_after_shutdown_mid_turn(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """SIGTERM'ing Sculptor mid-turn must not cause the prompt to be re-delivered.

    When Claude is killed by SIGTERM mid-turn the wrapper emits
    ``RequestStoppedAgentMessage`` for the in-flight chat. The sleeping turn
    produced no visible output, so on the next agent run the restart scan
    derives the prompt as settled (nothing is resumable) and
    ``_drop_already_processed_messages`` drops it from the queue. If the
    derivation instead left the prompt queued, the loop would re-push it to
    Claude, restarting the sleep.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(
            instance.page,
            prompt=_SLEEP_PROMPT,
            wait_for_agent_to_finish=False,
        )
        # Wait for the THINKING_INDICATOR — it only renders while Claude is
        # actively processing. ``data-status=RUNNING`` alone is not enough
        # because the spawner flips the task to RUNNING as soon as it picks
        # the task up, before Claude has spawned. Without an actually-in-flight
        # Claude turn, SIGTERM doesn't trigger the killed-request branch we
        # need to exercise.
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=_INFLIGHT_OBSERVATION_TIMEOUT_MS)

    # Exiting the context group SIGTERMs the backend, which propagates SIGTERM to
    # the fake-claude child process. The wrapper emits RequestStoppedAgentMessage
    # for the in-flight chat; that persisted stop (with no partial response) is
    # what the next run's scan settles the prompt on.

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)
        # After the BUILDING phase the agent should be idle (READY → read/unread
        # dot). If the prompt was replayed it would be RUNNING the sleep again
        # for ~120s (a "running" dot), so this expect would time out.
        expect(_agent_tab(instance.page)).to_have_attribute(
            "data-dot-status", _IDLE_DOT_STATUS, timeout=_SETTLE_TIMEOUT_MS
        )


@user_story("not have my AUQ-blocked prompt silently re-run after Sculptor restarts")
def test_chat_does_not_replay_after_shutdown_during_auq_wait(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Sculptor SIGTERM while waiting on an unanswered AUQ must not re-deliver the chat.

    In the AUQ-pending state the v1 loop deliberately clears
    ``user_input_message_being_processed = None`` while waiting for the
    answer, so restart handling must not key off that local. The restart
    scan (``scan_message_history``) sees the killed chat blocked on an
    unanswered question and derives it as settled rather than resumable
    (its question gate), so dedup drops the chat and the loop dispatches
    nothing post-restart: the restored question pins the task at WAITING.
    A raw re-delivery of the prompt would re-emit the AUQ tool block
    (duplicating the panel and producing observable activity from a "user
    did nothing" restart), and an auto-resume ("continue") would settle the
    turn and dismiss the question out from under the user.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(
            instance.page,
            prompt=_AUQ_PROMPT,
            wait_for_agent_to_finish=False,
        )
        # Wait for the AUQ panel — the agent must reach the waiting state before
        # we shut down, otherwise the test is exercising a different code path.
        auq_panel = get_ask_user_question_panel(instance.page)
        expect(auq_panel).to_be_visible(timeout=_INFLIGHT_OBSERVATION_TIMEOUT_MS)

    # SIGTERM during AUQ wait. The wrapper emits RequestStopped(chat); a raw
    # re-delivery of the chat would make Claude re-emit the AUQ tool block —
    # observable as the agent transitioning through RUNNING into WAITING again
    # post-restart.

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)
        # The unanswered question survives the restart, so the task settles to
        # WAITING either way — the dot can't discriminate a replay here. The
        # tool block count can: without a replay the single persisted AUQ
        # ToolUseBlock is restored as-is; a replayed chat would drive
        # fake_claude to re-emit the question as a SECOND tool block.
        auq_panel = get_ask_user_question_panel(instance.page)
        expect(auq_panel).to_be_visible(timeout=_SETTLE_TIMEOUT_MS)
        expect(_agent_tab(instance.page)).to_have_attribute("data-dot-status", "waiting", timeout=_SETTLE_TIMEOUT_MS)
        expect(get_ask_user_question_tool_blocks(instance.page)).to_have_count(1)
