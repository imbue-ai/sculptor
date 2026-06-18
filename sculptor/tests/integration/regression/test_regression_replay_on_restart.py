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

Other replay paths (disabled-resume FIXME; save/state-update race;
post-answer interrupted-completion reconciliation) require triggers
that ``SculptorInstanceFactory`` cannot reproduce — SIGKILL between two
specific transactions, or shutdown timed inside a millisecond-scale window.
Those bugs are covered by backend unit tests in
``sculptor/sculptor/tasks/handlers/run_agent/v1_test.py``.

Both tests use ``fake_claude:sleep`` (or the AUQ-emitting equivalent) for a
deterministic long-running turn so that any replay would keep the agent in
``RUNNING`` for at least 120 seconds. Each test asserts the post-restart
status reaches ``READY`` within a generous timeout — only true if the dedup
cursor correctly recorded the prompt as already-processed and the loop
therefore had nothing to dispatch.

Note on user-clicked Stop: the Stop button does NOT trigger this bug
class, because Claude's clean exit on a stdin interrupt control_request
flows through the wrapper's success branch (``RequestSuccessAgentMessage``
with ``interrupted=True``), which the v1 loop's existing
``is_agent_turn_finished`` check already correctly translates into a
``_update_task_state`` call. The bugs above only fire on the SIGTERM
path, where the wrapper's exception handler emits
``RequestStoppedAgentMessage`` and the loop's killed-request branch
short-circuits past the state-update site.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story
from sculptor.web.derived import TaskStatus

_SECONDS_MS = 1000

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
    """Click the persisted workspace tab on a fresh Sculptor instance."""
    layout = PlaywrightProjectLayoutPage(page)
    workspace_tab = layout.get_workspace_tabs().first
    expect(workspace_tab).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    workspace_tab.click()


def _agent_tab(page: Page) -> Locator:
    return PlaywrightAgentTabBarElement(page).get_agent_tabs().first


@user_story("not have my interrupted prompt silently re-run after Sculptor restarts")
def test_chat_does_not_replay_after_shutdown_mid_turn(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """SIGTERM'ing Sculptor mid-turn must not cause the prompt to be re-delivered.

    Reproduces hypothesis #1: when Claude is killed by SIGTERM mid-turn the
    wrapper emits ``RequestStoppedAgentMessage`` for the in-flight chat, and
    the v1 loop's killed-request branch short-circuits into
    ``_handle_completed_agent`` without bumping ``last_processed_message_id``.
    On the next agent run ``_drop_already_processed_messages`` leaves the
    prompt in the queue and the loop re-pushes it to Claude, restarting the
    sleep.
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
    # for the in-flight chat; the loop's killed-request branch returns into
    # _handle_completed_agent without updating last_processed (the bug).

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)
        # After the BUILDING phase the agent should be idle (READY). If the
        # prompt was replayed it would be RUNNING the sleep again for ~120s,
        # so this expect would time out.
        expect(_agent_tab(instance.page)).to_have_attribute(
            "data-status", TaskStatus.READY, timeout=_SETTLE_TIMEOUT_MS
        )


@user_story("not have my AUQ-blocked prompt silently re-run after Sculptor restarts")
def test_chat_does_not_replay_after_shutdown_during_auq_wait(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Sculptor SIGTERM while waiting on an unanswered AUQ must not re-deliver the chat.

    Reproduces hypothesis #4: the v1 loop's AUQ branch deliberately clears
    ``user_input_message_being_processed = None`` while waiting for the
    answer. Hypothesis #1's original fix keyed off
    that local, so it missed this case — the chat that triggered the AUQ
    never got recorded as processed, and on the next run it was re-delivered
    to Claude (which re-emitted the AUQ tool block, duplicating the panel
    and producing observable activity from a "user did nothing" restart).

    With the fix, the cursor advances on the wrapper's RequestStopped(chat)
    via ``_handle_completed_agent``'s scan, dedup drops the chat, and the
    agent stays idle post-restart.
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

    # SIGTERM during AUQ wait. The wrapper emits RequestStopped(chat); on the
    # next agent run (before the fix) the chat is re-delivered to Claude, which
    # re-emits the AUQ tool block — observable as the agent transitioning
    # through RUNNING into WAITING again post-restart.

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)
        # With the fix: BUILDING → READY (no replay; the historical AUQ
        # block doesn't pin to WAITING because the derived-status walk
        # breaks on the persisted RequestStopped). With the bug: BUILDING → RUNNING → WAITING (Claude
        # re-emits AUQ on the replayed chat), and ``READY`` is never
        # reached, so this expect times out.
        expect(_agent_tab(instance.page)).to_have_attribute(
            "data-status", TaskStatus.READY, timeout=_SETTLE_TIMEOUT_MS
        )
