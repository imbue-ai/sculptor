"""Regression tests for queued messages across backend restarts.

When Sculptor goes down while an agent is mid-turn with a follow-up message
queued behind it, the restart must recover BOTH messages correctly:

- the in-flight message must render exactly once as a sent message (the
  original bug rendered it a second time as a stuck queued message that never
  cleared, with a duplicate React key corrupting the virtualized chat list);
- the interrupted turn must reach a terminal state (no stuck
  Streaming/Thinking pill) — resumed and finished after a hard kill,
  finalized as stopped after a graceful shutdown;
- the queued follow-up must survive the restart and be dispatched exactly once
  after the interrupted turn settles (the bug left it queued forever because
  the resumed turn's completion never matched the original message id).

Two shutdown flavors are covered, and they recover via DIFFERENT paths:

- ``test_queued_message_dispatched_after_hard_kill_restart`` — SIGKILL via
  ``SculptorInstance.hard_kill()``: nothing terminal is persisted for the
  in-flight turn, so the next run re-queues it and takes the RESUME path.
  This is the literal trigger of the original bug (crash / OOM / power loss),
  and this test fails without the fixes.
- ``test_queued_message_dispatched_after_graceful_restart`` — normal SIGTERM
  teardown (quit and reopen): the wrapper persists a killed
  ``RequestStoppedAgentMessage`` for the in-flight turn and the run loop
  advances its processed-message cursor past that turn before exiting, so the
  next run does NOT resume it — the queued follow-up is dispatched fresh.
  This flavor recovers even without the original-bug fixes (verified by
  running it against the pre-fix code): it pins the everyday quit-and-reopen
  recovery contract rather than reproducing the bug. The resume path under a
  kill that lands mid-teardown is pinned at the loop layer instead (see
  ``test_resuming_in_flight_message_does_not_persist_a_duplicate``).

Both tests park the agent mid-turn with ``FakeClaudePause`` AFTER it has
streamed visible text. The streamed step's persisted ``ResponseBlock`` (flushed
by ``multi_step`` when the blocking ``wait_for_file`` step starts — see
``_INLINE_EMITTING_COMMANDS``) is what makes a hard-killed turn take the
RESUME path on the next run rather than re-sending the prompt from scratch,
matching the real-world bug.

Millisecond-precise kill windows (e.g. SIGKILL between two specific
transactions) cannot be reproduced at this layer; those are pinned by backend
unit tests in ``sculptor/sculptor/tasks/handlers/run_agent/v1_test.py``.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.backend_contract import TaskStatus
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_SECONDS_MS = 1000

# Visibility gate for the post-restart page — generous because the Phase-2
# backend is restoring a previously-running task and CI can be slow.
_RESTART_VISIBILITY_TIMEOUT_MS = 60 * _SECONDS_MS

# Window for the post-restart task to resume the interrupted turn, complete it,
# dispatch the queued follow-up, and settle into READY.
_SETTLE_TIMEOUT_MS = 60 * _SECONDS_MS

# Streamed by the agent BEFORE it parks on the pause sentinel. Its presence in
# the transcript proves a partial response reached the backend before the
# shutdown (the precondition for the hard-kill resume path); its count pins
# the no-duplication contract after restart.
_PARTIAL_RESPONSE_MARKER = "PARTIAL_RESPONSE_BEFORE_RESTART"

_QUEUED_FOLLOWUP_TEXT = "queued follow-up across restart"


def _paused_mid_turn_prompt(pause: FakeClaudePause) -> str:
    """One agent turn: stream visible text, then park on the pause sentinel.

    ``stream_text`` emits its streaming events inline and ``multi_step``
    flushes its full assistant message when the blocking ``wait_for_file``
    step starts, so by the time the agent is parked the backend has a
    persisted ResponseBlock for the turn — killing it now leaves exactly the
    "in-flight with partial response" state that the original bug starts from.
    """
    return f"""\
fake_claude:multi_step `{{
  "steps": [
    {{"command": "stream_text", "args": {{"text": "{_PARTIAL_RESPONSE_MARKER}", "delay_seconds": 0}}}},
    {{"command": "wait_for_file", "args": {{"path": "{pause.release_path}"}}}}
  ]
}}`"""


def _start_paused_turn_and_queue_followup(instance: SculptorInstance, pause: FakeClaudePause) -> None:
    """Start the paused turn, wait for the streamed marker, queue the follow-up."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=instance.page,
        prompt=_paused_mid_turn_prompt(pause),
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    # The streamed text must have flowed through the backend before we shut it
    # down — this is what puts the persisted partial response on disk that the
    # next run resumes from. (The queued-message round trips below give the
    # ~1s-cadence agent loop ample time to save the flushed ResponseBlock.)
    # Assistant messages only: the prompt's multi_step JSON also contains the
    # marker text, so an unscoped filter would match the user message too.
    expect(chat_panel.get_assistant_messages().filter(has_text=_PARTIAL_RESPONSE_MARKER)).to_have_count(1)

    send_chat_message(chat_panel=chat_panel, message=_QUEUED_FOLLOWUP_TEXT)
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    expect(chat_panel.get_queued_message_bar()).to_contain_text(_QUEUED_FOLLOWUP_TEXT)


def _open_workspace_after_restart(page: Page) -> PlaywrightChatPanelElement:
    """Click the persisted workspace tab on a fresh Sculptor instance."""
    layout = PlaywrightProjectLayoutPage(page)
    workspace_tab = layout.get_workspace_tabs().first
    expect(workspace_tab).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    workspace_tab.click()
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    return chat_panel


def _agent_tab(page: Page) -> Locator:
    return PlaywrightAgentTabBarElement(page).get_agent_tabs().first


def _assert_recovered_transcript(page: Page, chat_panel: PlaywrightChatPanelElement) -> None:
    """The post-restart contract shared by both shutdown flavors."""
    # The interrupted turn reaches a terminal state — resumed and completed
    # after a hard kill (FakeClaude answers the resume's "continue" instruction
    # with its default response), finalized by the persisted killed
    # RequestStopped after a graceful shutdown — then the queued follow-up is
    # dispatched and completes, and only then does the task settle into READY.
    # With the original bug the follow-up was never dispatched and the task
    # stayed RUNNING with a stuck Thinking pill, so this expect times out.
    expect(_agent_tab(page)).to_have_attribute("data-status", TaskStatus.READY, timeout=_SETTLE_TIMEOUT_MS)

    # The follow-up was dequeued (not stuck in the queued bar forever)...
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    # ...and rendered exactly once as a sent message.
    expect(chat_panel.get_messages().filter(has_text=_QUEUED_FOLLOWUP_TEXT)).to_have_count(1)

    # The interrupted turn's content survived and was not duplicated: the
    # original user message and its partial response each render exactly once
    # (the bug rendered the user message twice — once sent, once stuck-queued).
    # The marker check is scoped to assistant messages because the prompt's
    # multi_step JSON contains the marker text too.
    expect(chat_panel.get_messages().filter(has_text="fake_claude:multi_step")).to_have_count(1)
    expect(chat_panel.get_assistant_messages().filter(has_text=_PARTIAL_RESPONSE_MARKER)).to_have_count(1)

    # Nothing is left mid-turn.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()


@user_story("my queued message to be sent after Sculptor recovers from a crash")
def test_queued_message_dispatched_after_hard_kill_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """SIGKILL mid-turn with a queued follow-up: restart recovers both messages.

    The hard-kill repro: the backend dies without persisting any completion for
    the in-flight turn. On restart the turn must be resumed (not replayed from
    scratch, not duplicated), and the queued follow-up must be dispatched when
    the resumed turn completes — which only happens when the resumed turn's
    completion is keyed on the ORIGINAL message id (``for_user_message_id``).
    """
    pause = FakeClaudePause()
    with sculptor_instance_factory_.spawn_instance() as instance:
        _start_paused_turn_and_queue_followup(instance, pause)
        instance.hard_kill()

    # Defensive: the resume path never re-runs the original multi_step prompt,
    # but if recovery ever regressed to a fresh re-send, releasing the pause
    # lets that turn finish (and the marker would then render twice, failing
    # the count assertion below) instead of hanging the whole test.
    pause.release()

    with sculptor_instance_factory_.spawn_instance() as instance:
        chat_panel = _open_workspace_after_restart(instance.page)
        _assert_recovered_transcript(instance.page, chat_panel)


@user_story("my queued message to be sent after I quit and reopen Sculptor mid-task")
def test_queued_message_dispatched_after_graceful_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """SIGTERM mid-turn with a queued follow-up: restart recovers both messages.

    The everyday flavor: quitting Sculptor delivers SIGTERM, so the wrapper
    persists a killed ``RequestStoppedAgentMessage`` for the in-flight turn and
    the run loop advances its processed-message cursor past that turn before
    exiting. The next run therefore does NOT resume the interrupted turn — the
    killed completion finalizes it — and must dispatch the queued follow-up
    fresh, exactly once. This contract held even before the hard-kill fixes
    landed, so this is defensive coverage of the quit-and-reopen path rather
    than a repro of the original bug; the resume path is exercised by the
    hard-kill test above and by the loop-level window tests in ``v1_test.py``.
    """
    pause = FakeClaudePause()
    with sculptor_instance_factory_.spawn_instance() as instance:
        _start_paused_turn_and_queue_followup(instance, pause)
        # Exiting the block SIGTERMs the backend, which propagates to the
        # parked fake-claude turn (RequestStopped persisted, no clean finish).

    # Defensive, same as the hard-kill test.
    pause.release()

    with sculptor_instance_factory_.spawn_instance() as instance:
        chat_panel = _open_workspace_after_restart(instance.page)
        _assert_recovered_transcript(instance.page, chat_panel)
