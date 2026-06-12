"""Tests for the turn footer in the alpha chat view.

Verifies that:
1. After a normal completed turn, the footer shows duration and token count
   (e.g. "0.0s · 0 tokens").
2. The "Stopped" footer always appears after interrupting a turn,
   even when no content was streamed before the stop.
3. The "Stopped" footer includes duration metadata (not just the word "Stopped").
4. The footer duration reflects the full wall-clock turn time, not just the
   LLM API call duration.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A prompt that produces text output and then stays busy, giving time to interrupt
# after content has already been streamed.
_TEXT_THEN_SLOW_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "text", "args": {"text": "Here is some content before the long operation."}},
    {"command": "bash", "args": {"command": "sleep 30"}},
    {"command": "text", "args": {"text": "Done."}}
  ]
}`"""

# A prompt that just sleeps — agent stays busy with no text output.
_SLEEP_PROMPT = 'fake_claude:sleep `{"seconds": 120}`'


def _stop_agent_via_status_pill(chat_panel: PlaywrightChatPanelElement) -> None:
    """Click the stop button on the status pill and wait for it to complete."""
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).not_to_be_visible()


@user_story("to see 'Stopped' footer with duration after interrupting a turn that has streamed content")
def test_stopped_turn_footer_shows_duration_after_content_streamed(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the user stops a turn after content has been streamed, the turn footer
    should display 'Stopped' along with the duration (e.g. 'Stopped · 3.2s').
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_TEXT_THEN_SLOW_PROMPT,
        wait_for_agent_to_finish=False,
    )

    alpha_view = get_alpha_chat_view(page)
    chat_panel = task_page.get_chat_panel()

    # Wait for assistant text to appear in the alpha view before stopping
    alpha_text = alpha_view.get_text_blocks()
    expect(alpha_text.first).to_be_visible()
    expect(alpha_text.first).to_contain_text("Here is some content")

    _stop_agent_via_status_pill(chat_panel)

    # The turn footer should be visible
    turn_footer = alpha_view.get_turn_footers()
    expect(turn_footer).to_be_visible()

    # It must say "Stopped"
    expect(turn_footer).to_contain_text("Stopped")

    # It must also include duration info (contains "s" for seconds, e.g. "3.2s")
    # The pattern is "Stopped · X.Xs" — the "s" suffix after a digit indicates duration.
    expect(turn_footer).to_contain_text("s")


@user_story("to see 'Stopped' footer appear even when no content was streamed before stopping")
def test_stopped_turn_footer_visible_when_stopped_before_content(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the user stops a turn before any assistant content has been streamed,
    a turn footer with 'Stopped' should still appear so the user has feedback
    that the turn was interrupted.
    """
    page = sculptor_instance_.page

    # First, send a normal message to establish the chat, then send a slow one and interrupt.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Ready."}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a slow message and immediately stop
    send_chat_message(chat_panel=chat_panel, message=_SLEEP_PROMPT)

    _stop_agent_via_status_pill(chat_panel)

    # There should be a turn footer with "Stopped" visible in the alpha view
    alpha_view = get_alpha_chat_view(page)
    turn_footers = alpha_view.get_turn_footers()
    # We expect at least one footer that says "Stopped" (the interrupted turn).
    # The first turn may also have a footer with metrics.
    stopped_footer = turn_footers.filter(has_text="Stopped")
    expect(stopped_footer.first).to_be_visible()


@user_story("to see duration and token count in the turn footer after a completed turn")
def test_turn_footer_shows_metrics_after_completed_turn(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After a normal (non-stopped) agent turn completes, the turn footer should
    display duration and token count (e.g. "0.0s · 0 tokens").
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Done."}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    turn_footer = alpha_view.get_turn_footers()
    expect(turn_footer).to_be_visible()
    expect(turn_footer).to_contain_text("s")
    # Token count should also be present
    expect(turn_footer).to_contain_text("tokens")


# A prompt that runs a 2-second bash sleep so the turn takes measurable wall-clock time.
# FakeClaude hardcodes duration_ms to 0, so the footer should show the real elapsed time
# (>= 1.5s), not the API-reported 0.0s.
_DELAYED_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "sleep 2"}},
    {"command": "text", "args": {"text": "Done after delay."}}
  ]
}`"""


@user_story("to see a turn footer duration that reflects the actual wall-clock time, not just the API call duration")
def test_turn_footer_duration_reflects_wall_clock_time(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The turn footer should show the full wall-clock turn duration, not the
    LLM API response time. FakeClaude reports duration_ms=0, so if the footer
    shows 0.0s after a 2-second bash sleep, the duration source is wrong.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_DELAYED_PROMPT,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    turn_footer = alpha_view.get_turn_footers()
    expect(turn_footer).to_be_visible()

    # Wait for footer text to contain a duration pattern before reading it
    expect(turn_footer).to_contain_text(re.compile(r"\d+\.\d+s"))

    # Extract the duration number from the footer text (e.g. "2.3s · 0 tokens" → 2.3)
    footer_text = turn_footer.inner_text()
    match = re.search(r"(\d+\.\d+)s", footer_text)
    assert match is not None, f"Expected duration in footer text: {footer_text}"
    duration = float(match.group(1))

    # The bash sleep is 2 seconds, so wall-clock duration must be at least 1.5s.
    # With the bug (using API-reported duration_ms=0), this shows 0.0s and fails.
    assert duration >= 1.5, f"Expected duration >= 1.5s, got {duration}s. Footer: {footer_text}"
