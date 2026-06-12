"""Tests for the interrupt and continue functionality.

Verifies that:
1. Interrupting the agent shows the "Stopped" marker in the chat.
2. The agent can be interrupted before any output and after previous messages.
3. The agent can continue working after being interrupted.
"""

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A prompt that just sleeps — agent stays busy with no output.
_SLEEP_PROMPT = 'fake_claude:sleep `{"seconds": 120}`'

# A prompt that produces text output and completes immediately.
_TEXT_PROMPT = 'fake_claude:text `{"text": "Here is some content."}`'


def _interrupt_agent_before_any_output(chat_panel: PlaywrightChatPanelElement) -> None:
    """Interrupt the agent before any output is generated."""
    # The stop button only renders while the indicator is visible — wait for it
    # to mount before trying to click, otherwise we race the backend.
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()


@user_story("to interrupt the agent while it's working")
def test_interrupt_initial_message_immediately(sculptor_instance_: SculptorInstance) -> None:
    """Test that interrupting the initial message immediately does not show a warning.

    When the user sends a message and quickly clicks Stop before the session ID
    is fully written, an InterruptFailure may occur internally. This should be
    handled silently — the interrupt works correctly and the user message is
    rolled back, which is the expected behavior.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=_SLEEP_PROMPT,
        wait_for_agent_to_finish=False,
    )

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    _interrupt_agent_before_any_output(chat_panel=chat_panel)

    # Verify no InterruptFailure warning is shown to the user.
    expect(chat_panel.get_messages().filter(has_text="InterruptFailure")).to_have_count(0)
    expect(chat_panel.get_messages().filter(has_text="Failed to interrupt")).to_have_count(0)


@user_story("to see the Stopped marker after interrupting a turn")
def test_interrupt_shows_stopped_indicator(sculptor_instance_: SculptorInstance) -> None:
    """After a completed first turn, sending a second message and interrupting it
    should show the 'Stopped' marker on the interrupted assistant message."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=_TEXT_PROMPT,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Verify initial text appeared
    expect(chat_panel.get_messages().nth(1)).to_contain_text("Here is some content.")

    # Send a slow message and interrupt it
    send_chat_message(chat_panel=chat_panel, message=_SLEEP_PROMPT)
    _interrupt_agent_before_any_output(chat_panel=chat_panel)

    # The interrupted assistant message footer shows "Stopped · <elapsed>".
    expect(chat_panel.get_messages().last).to_contain_text("Stopped")


# Default keybinding for the `interrupt_agent` action. Mirrors the SIGINT
# convention CLI users expect.
_INTERRUPT_KEY = "Control+c"


@user_story("to interrupt the agent by pressing Ctrl+C in the chat input")
def test_ctrl_c_in_chat_input_interrupts_agent(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Ctrl+C while focused in the chat input interrupts the running agent.

    The keybinding gates on the alpha StatusPill's `isCancellable` signal.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=_TEXT_PROMPT,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a slow prompt so the agent stays busy while we press Ctrl+C.
    send_chat_message(chat_panel=chat_panel, message=_SLEEP_PROMPT)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    chat_input = chat_panel.get_chat_input()
    chat_input.click()
    chat_input.press(_INTERRUPT_KEY)

    # Alpha-view stop marker — the assistant message footer shows
    # "Stopped · <elapsed>" instead of legacy's "Interrupted by user".
    expect(chat_panel.get_messages().last).to_contain_text("Stopped")
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()


@user_story("to see the Stopping indicator while Ctrl+C interrupts the agent")
def test_ctrl_c_shows_stopping_indicator_in_alpha_view(sculptor_instance_: SculptorInstance) -> None:
    """Ctrl+C must transition the status pill to the 'Stopping...' label.

    Regression: the pill kept its own local React state for the in-flight
    flag, so a sibling component triggering the interrupt (the keybinding in
    ChatInput) would update the agent but never flip the pill's display.
    The interrupt endpoint is also delayed so the brief 'Stopping...' window
    is wide enough to assert on without flakiness.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=_SLEEP_PROMPT,
        wait_for_agent_to_finish=False,
    )

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    def _slow_interrupt(route: Route) -> None:
        sculptor_instance_.page.wait_for_timeout(2000)
        route.continue_()

    sculptor_instance_.page.route("**/agents/*/interrupt", _slow_interrupt)

    chat_input = chat_panel.get_chat_input()
    chat_input.click()
    chat_input.press(_INTERRUPT_KEY)

    pill_label = chat_panel.get_status_pill_label()
    expect(pill_label).to_have_text("Stopping...")


@user_story("to press Ctrl+C repeatedly without firing the interrupt more than once")
def test_ctrl_c_spam_only_interrupts_once(sculptor_instance_: SculptorInstance) -> None:
    """Hammering Ctrl+C must not produce multiple interrupt requests.

    Regression: the in-flight interrupt flag is shared with the Stop button so
    repeated presses (while the previous request is still settling) are no-ops
    instead of stacking up extra "Stopped" entries in chat.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=_TEXT_PROMPT,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    interrupt_calls: list[str] = []
    sculptor_instance_.page.on(
        "request",
        lambda req: interrupt_calls.append(req.url) if "/interrupt" in req.url else None,
    )

    send_chat_message(chat_panel=chat_panel, message=_SLEEP_PROMPT)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    chat_input = chat_panel.get_chat_input()
    chat_input.click()
    for _ in range(5):
        chat_input.press(_INTERRUPT_KEY)

    expect(chat_panel.get_messages().last).to_contain_text("Stopped")
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    assert len(interrupt_calls) == 1, (
        f"expected exactly 1 interrupt POST, got {len(interrupt_calls)}: {interrupt_calls}"
    )


@user_story("to interrupt the agent and then continue with a new message")
def test_interrupt_and_continue(sculptor_instance_: SculptorInstance) -> None:
    """After interrupting, the agent can process a new message successfully."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=_TEXT_PROMPT,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a slow message and interrupt it
    send_chat_message(chat_panel=chat_panel, message=_SLEEP_PROMPT)
    _interrupt_agent_before_any_output(chat_panel=chat_panel)

    # Verify the Stopped marker is present
    expect(chat_panel.get_messages().last).to_contain_text("Stopped")

    # Send a follow-up message and verify the agent can still respond
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:text `{"text": "Follow-up response."}`',
    )

    # Wait for the follow-up to complete. The exact count depends on whether
    # the interrupted turn produced an empty assistant message, so just wait
    # for the agent to finish and check for the follow-up text.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30000)
    expect(chat_panel.get_messages().last).to_contain_text("Follow-up response.")
