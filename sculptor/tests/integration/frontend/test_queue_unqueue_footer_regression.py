"""End-to-end regression for SCU-1820: unqueuing a message while an agent turn
is still running must not stamp a spurious turn footer.

Repro shape (reported live): while the agent waits for a background task its
foreground turn has already emitted its turn-end, so the turn's metrics are
pending, but the request stays open — RequestSuccess for the real turn has not
arrived because the background task_notification is still outstanding. Queue a
message and then unqueue it in that window: the RemoveQueuedMessage lifecycle
emits its OWN RequestStarted/RequestSuccess pair, and the RequestSuccess branch
of message_conversion used to run end-of-turn side effects for it — stamping the
pending turn metrics onto the in-progress message as a turn footer (token
counts) and clearing the background-wait state. It survived a hard reload.

FakeClaude's plain background hold does not reproduce this: the output processor
stashes the turn's metrics and only emits TurnMetricsAgentMessage once the CLI
answers a get_context_usage control request, which the paused handler never
does. The ``answer_context_usage`` flag on ``background_subagent`` makes
FakeClaude answer it during the hold (as real Claude does), so the metrics
become pending mid-hold and the bug reproduces end-to-end (see SCU-1823).
"""

import json

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to not see a spurious turn footer after unqueuing a message during a background-task wait")
def test_unqueue_during_background_wait_does_not_show_turn_footer(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Queuing then unqueuing a message while the agent waits on a background
    task must NOT make a turn footer appear on the still-running turn — including
    after a hard reload — and must not clear the background-wait state."""
    page = sculptor_instance_.page

    # Queuing only happens when always-interrupt-and-send is OFF; a sibling test
    # in the shared session may have enabled it, so disable it defensively.
    # start_task_and_wait_for_ready navigates to workspace creation from here, so
    # there's no need to route back through the (hash-history-flaky) go_back().
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.disable_always_interrupt()

    # Park the agent in the background-wait window AND answer get_context_usage
    # during the hold, so the turn's metrics are flushed and pending while the
    # request is still open.
    pause = FakeClaudePause()
    bg_command = (
        "fake_claude:background_subagent `"
        + json.dumps(
            {
                "description": "Find Python files",
                "summary_text": "background subagent done",
                "pause_path": str(pause.release_path),
                "answer_context_usage": True,
            }
        )
        + "`"
    )
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=bg_command,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    alpha_view = get_alpha_chat_view(page)

    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="Background subagent launched").first).to_be_visible()
    expect(chat_panel.get_status_pill()).to_have_attribute("data-agent-state", "waiting_for_background")

    # Baseline: the turn is still running — its metrics are only pending, not
    # attached — so there is no footer yet.
    expect(alpha_view.get_turn_footers()).to_have_count(0)

    # Queue a message, then unqueue it via the trash/cancel button (the
    # RemoveQueuedMessage lifecycle). force=True bypasses the opacity:0
    # hover-reveal on the cancel button.
    send_chat_message(chat_panel=chat_panel, message="test")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    chat_panel.get_queued_message_cancel_button().click(force=True)
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    # Hard reload. The derived state rebuilds atomically from the persisted
    # message log, so once the "launched" message is back the state (including
    # any erroneously-attached footer) is fully applied — no transient race.
    soft_reload_page(page)
    expect(chat_panel).to_be_visible()
    expect(chat_panel.get_messages().filter(has_text="Background subagent launched").first).to_be_visible()

    # The bug: a turn footer (token count) is stamped onto the still-running
    # message and survives the reload, and the background-wait state is cleared.
    # Neither must happen — the turn has not finished.
    expect(get_alpha_chat_view(page).get_turn_footers()).to_have_count(0)
    expect(chat_panel.get_status_pill()).to_have_attribute("data-agent-state", "waiting_for_background")

    # Let the agent finish so the shared instance is left idle for later tests.
    pause.release()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30_000)
