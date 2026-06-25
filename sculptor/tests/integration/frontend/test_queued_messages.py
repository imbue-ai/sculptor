"""Integration tests for queued message behavior."""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.base import wait_for_one_frame
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _start_busy_agent(sculptor_instance: SculptorInstance, sleep_seconds: int = 15):
    """Start a task with a long-running fake_claude:sleep so we can queue messages."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt=f'fake_claude:sleep `{{"seconds": {sleep_seconds}}}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    return task_page, chat_panel


@user_story("to edit a queued message and send a new one while agent is busy")
def test_message_queues_after_editing_queued_message(sculptor_instance_: SculptorInstance) -> None:
    """After editing a queued message, sending a new message should still queue it.

    Regression: editing a queued message triggered a RemoveQueuedMessage request
    whose RequestStarted/RequestSuccess lifecycle clobbered the current_request_id,
    making the frontend think the agent was no longer busy. New messages then
    appeared inline in chat instead of being queued.
    """
    # Start a task with a long-running agent so we can queue messages.
    # Use 30s (not the 15s default) because the Edit click deletes the queued
    # message server-side, leaving the agent with an empty queue. If the sleep
    # elapses before the test re-sends, the resend lands inline instead of
    # being queued — see _start_busy_agent for context.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:sleep `{"seconds": 30}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for agent to be actively streaming
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Send a message while agent is busy — it should be queued
    send_chat_message(chat_panel=chat_panel, message="message to edit")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Click edit (force=True bypasses opacity:0 visibility check)
    chat_panel.get_queued_message_edit_button().click(force=True)

    # The queued message is removed and its text moves into the editor
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_have_text("message to edit")

    # Send the message again (agent is still busy, so it should re-queue)
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")

    # CRITICAL: The new message must be queued, not promoted inline into chat
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)


@user_story("to see a queued message bar with action buttons when a message is queued")
def test_queued_message_bar_appears_and_shows_content(sculptor_instance_: SculptorInstance) -> None:
    """Queued message bar appears with correct content and action buttons."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)

    send_chat_message(chat_panel=chat_panel, message="queued content here")

    queued_bar = chat_panel.get_queued_message_bar()
    expect(queued_bar).to_have_count(1)

    expect(queued_bar).to_contain_text("queued content here")

    # Send button is always visible; edit/cancel are in the DOM but hidden via opacity
    expect(chat_panel.get_queued_message_send_button()).to_be_visible()
    expect(chat_panel.get_queued_message_edit_button()).to_be_attached()
    expect(chat_panel.get_queued_message_cancel_button()).to_be_attached()


@user_story("to prevent sending a second message while one is already queued")
def test_chat_input_disabled_while_message_queued(sculptor_instance_: SculptorInstance) -> None:
    """Send button is disabled while a message is queued; re-enabled after cancel."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)

    send_chat_message(chat_panel=chat_panel, message="queued message")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Send button should be disabled while a message is queued
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_disabled()

    # Cancel the queued message (force=True bypasses opacity:0 visibility check)
    chat_panel.get_queued_message_cancel_button().click(force=True)
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    # Type text so send button becomes enabled
    page = chat_panel._page
    chat_input = chat_panel.get_chat_input()
    type_into_tiptap(page, chat_input, "new message")
    expect(send_button).to_be_enabled()


@user_story("to cancel a queued message and continue chatting")
def test_cancel_queued_message(sculptor_instance_: SculptorInstance) -> None:
    """Canceling a queued message removes the bar and agent keeps streaming."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)

    send_chat_message(chat_panel=chat_panel, message="message to cancel")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Click cancel (force=True bypasses opacity:0 visibility check)
    chat_panel.get_queued_message_cancel_button().click(force=True)

    # Bar disappears, agent is still streaming
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()


@user_story("to interrupt the agent and send a queued message immediately")
def test_interrupt_and_send_queued_message(sculptor_instance_: SculptorInstance) -> None:
    """Interrupt-and-send stops the agent and promotes the queued message."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)

    send_chat_message(chat_panel=chat_panel, message='fake_claude:text `{"text": "promoted response"}`')
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    chat_panel.get_queued_message_send_button().click()

    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    # Wait for the promoted message to be processed by the agent.
    # The interrupted fake_claude:sleep produces no visible text, so we get
    # 3 messages: user1 (sleep) + user2 (promoted) + assistant2 (response).
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)


@user_story("to see a spinner while interrupt is in flight")
def test_interrupt_and_send_shows_spinner_while_in_flight(sculptor_instance_: SculptorInstance) -> None:
    """The interrupt button shows a spinner and is disabled while interrupting."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)

    send_chat_message(chat_panel=chat_panel, message='fake_claude:text `{"text": "response"}`')
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    send_button = chat_panel.get_queued_message_send_button()
    expect(send_button).to_be_enabled()

    send_button.click()

    # The bar should eventually disappear (interrupt completes)
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)


@user_story("to see a queued message promoted when the agent finishes")
def test_queued_message_promoted_when_agent_finishes(sculptor_instance_: SculptorInstance) -> None:
    """Queued message is promoted and processed when the agent finishes."""
    pause = FakeClaudePause()
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=pause.prompt,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    send_chat_message(chat_panel=chat_panel, message="follow-up message")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    pause.release()

    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30000)


@user_story("to edit a queued message by moving it into an empty editor")
def test_edit_queued_message_into_empty_editor(sculptor_instance_: SculptorInstance) -> None:
    """Editing a queued message with an empty editor moves text to editor without dialog."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)

    send_chat_message(chat_panel=chat_panel, message="queued text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Ensure editor is empty
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_have_text("")

    # Click edit (force=True bypasses opacity:0 visibility check)
    chat_panel.get_queued_message_edit_button().click(force=True)

    # Bar disappears, text moves to editor, no dialog
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_input).to_have_text("queued text")


@user_story("to see a dialog when editing a queued message while editor has text")
def test_edit_with_text_in_editor_shows_dialog(sculptor_instance_: SculptorInstance) -> None:
    """A dialog appears when editing a queued message and the editor already has text."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)
    page = chat_panel._page

    send_chat_message(chat_panel=chat_panel, message="queued text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Type draft text into the editor (editor is now empty after sending)
    chat_input = chat_panel.get_chat_input()
    type_into_tiptap(page, chat_input, "draft text")
    expect(chat_input).to_have_text("draft text")
    # Wait for React to re-render QueuedMessageBar with updated promptDraft atom
    wait_for_one_frame(page)

    # Click edit — undo dialog should appear (force=True bypasses opacity:0)
    chat_panel.get_queued_message_edit_button().click(force=True)

    # Dialog should appear with all three buttons
    expect(chat_panel.get_undo_queued_message_dialog()).to_be_visible()
    expect(chat_panel.get_undo_queued_message_cancel_button()).to_be_visible()
    expect(chat_panel.get_undo_queued_message_remove_button()).to_be_visible()
    expect(chat_panel.get_undo_queued_message_overwrite_button()).to_be_visible()


@user_story("to overwrite editor content with queued message text via dialog")
def test_edit_dialog_overwrite_replaces_editor_content(sculptor_instance_: SculptorInstance) -> None:
    """Overwrite editor option replaces editor content with the queued message text."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)
    page = chat_panel._page
    chat_input = chat_panel.get_chat_input()

    # Queue a message, then type draft text
    send_chat_message(chat_panel=chat_panel, message="queued text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    type_into_tiptap(page, chat_input, "draft text")
    expect(chat_input).to_have_text("draft text")
    # Wait for React to re-render QueuedMessageBar with updated promptDraft atom
    wait_for_one_frame(page)

    # Click edit → dialog appears (force=True bypasses opacity:0)
    chat_panel.get_queued_message_edit_button().click(force=True)
    expect(chat_panel.get_undo_queued_message_dialog()).to_be_visible()

    # Click "Overwrite editor"
    chat_panel.get_undo_queued_message_overwrite_button().click()

    # Dialog closes, editor has queued text, bar is gone
    expect(chat_panel.get_undo_queued_message_dialog()).not_to_be_visible()
    expect(chat_input).to_have_text("queued text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()


@user_story("to remove a queued message via dialog")
def test_edit_dialog_remove_discards_queued_message(sculptor_instance_: SculptorInstance) -> None:
    """Remove button discards the queued message and keeps editor text."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)
    page = chat_panel._page
    chat_input = chat_panel.get_chat_input()

    # Queue a message, then type draft text
    send_chat_message(chat_panel=chat_panel, message="queued text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    type_into_tiptap(page, chat_input, "draft text")
    expect(chat_input).to_have_text("draft text")
    # Wait for React to re-render QueuedMessageBar with updated promptDraft atom
    wait_for_one_frame(page)

    # Click edit → dialog appears (force=True bypasses opacity:0)
    chat_panel.get_queued_message_edit_button().click(force=True)
    expect(chat_panel.get_undo_queued_message_dialog()).to_be_visible()

    # Click "Remove"
    chat_panel.get_undo_queued_message_remove_button().click()

    # Dialog closes, editor still has draft text, bar is gone
    expect(chat_panel.get_undo_queued_message_dialog()).not_to_be_visible()
    expect(chat_input).to_have_text("draft text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()


@user_story("to keep a queued message when canceling the edit dialog")
def test_edit_dialog_cancel_requeues_message(sculptor_instance_: SculptorInstance) -> None:
    """Cancel in the edit dialog re-queues the message (delete-then-requeue round-trip)."""
    # Use 30s (not the 15s default) because Edit click deletes the queued
    # message before the dialog opens. If the sleep elapses before Cancel
    # fires the re-send, the requeue lands inline rather than queued.
    _, chat_panel = _start_busy_agent(sculptor_instance_, sleep_seconds=30)
    page = chat_panel._page
    chat_input = chat_panel.get_chat_input()

    # Queue a message, then type draft text
    send_chat_message(chat_panel=chat_panel, message="queued text")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    type_into_tiptap(page, chat_input, "draft text")
    expect(chat_input).to_have_text("draft text")
    # Wait for React to re-render QueuedMessageBar with updated promptDraft atom
    wait_for_one_frame(page)

    # Click edit → dialog appears (force=True bypasses opacity:0)
    chat_panel.get_queued_message_edit_button().click(force=True)
    expect(chat_panel.get_undo_queued_message_dialog()).to_be_visible()

    # Click "Cancel" (keep queued)
    chat_panel.get_undo_queued_message_cancel_button().click()

    # Dialog closes, editor still has draft text
    expect(chat_panel.get_undo_queued_message_dialog()).not_to_be_visible()
    expect(chat_input).to_have_text("draft text")

    # Message should be re-queued (bar reappears)
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    expect(chat_panel.get_thinking_indicator()).to_be_visible()


@user_story("to see a queued message survive a page refresh")
def test_queued_message_persists_across_page_refresh(sculptor_instance_: SculptorInstance) -> None:
    """Queued message is restored from server-side state after page reload."""
    # Use 30s (not the 15s default) so the agent stays busy through the
    # soft_reload_page round-trip. If the sleep elapses mid-reload, the
    # queued message gets promoted/consumed and the bar never reappears.
    _, chat_panel = _start_busy_agent(sculptor_instance_, sleep_seconds=30)

    send_chat_message(chat_panel=chat_panel, message="persistent message")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    page = chat_panel._page
    soft_reload_page(page)

    # Wait for chat panel to re-appear (locators are lazy, so the POM
    # resolves against the new DOM after reload)
    expect(chat_panel).to_be_visible()

    # Queued message bar should be restored
    queued_bar = chat_panel.get_queued_message_bar()
    expect(queued_bar).to_have_count(1)
    expect(queued_bar).to_contain_text("persistent message")


@user_story("to send messages immediately when always-interrupt is enabled")
def test_always_interrupt_setting_bypasses_queue(sculptor_instance_: SculptorInstance) -> None:
    """With always-interrupt enabled, sending a message interrupts instead of queuing."""
    page = sculptor_instance_.page

    # Enable always-interrupt via the settings UI so the server persists the
    # setting and the frontend picks it up on subsequent navigations.
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_always_interrupt()

    _, chat_panel = _start_busy_agent(sculptor_instance_)

    # Send a message while agent is busy — with always-interrupt enabled,
    # handleSend calls sendMessage() then interruptWorkspaceAgent() asynchronously.
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:text `{"text": "interrupt response"}`',
    )

    # The message should be sent and agent interrupted — no queued bar
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    # The interrupted sleep + user message + agent response = 3 messages.
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)

    # Reset always-interrupt before returning to the shared sculptor_instance_
    # so later tests in the same session see the default OFF state.
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.disable_always_interrupt()


@user_story("to keep an existing queued message when always-interrupt is toggled on")
def test_always_interrupt_setting_does_not_affect_existing_queued_message(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Toggling always-interrupt on does not affect an already-queued message."""
    page = sculptor_instance_.page

    # Ensure always-interrupt is OFF before starting, since a previous test
    # in the same session may have enabled it (the shared sculptor_instance_
    # persists backend config across tests).
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.disable_always_interrupt()
    page.go_back()

    # Start a busy agent and queue a message BEFORE enabling always-interrupt.
    # Use a longer sleep because this test navigates to settings and back,
    # which can take extra time on slow CI runners.
    task_page, chat_panel = _start_busy_agent(sculptor_instance_, sleep_seconds=60)
    send_chat_message(chat_panel=chat_panel, message="already queued")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Enable always-interrupt via the settings UI, then navigate back
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_always_interrupt()

    # Navigate back to the workspace by clicking its tab in the top bar.
    # This is more reliable than page.go_back() which depends on browser
    # history state that can be unpredictable with hash-based routing.
    task_page.get_workspace_tabs().click()

    # Wait for the chat panel to re-appear and the agent to still be streaming
    # (confirms the WebSocket reconnected and delivered the initial state).
    expect(chat_panel).to_be_visible()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # The existing queued message should still be visible.
    queued_bar = chat_panel.get_queued_message_bar()
    expect(queued_bar).to_have_count(1)


@user_story("to interrupt the agent and send a message via keyboard shortcut")
def test_keyboard_shortcut_interrupt_and_send(sculptor_instance_: SculptorInstance) -> None:
    """Meta+Shift+Enter sends the message and interrupts the agent immediately."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)
    page = chat_panel._page

    # Type a fake_claude command so we get a deterministic response to wait for
    chat_input = chat_panel.get_chat_input()
    type_into_tiptap(page, chat_input, 'fake_claude:text `{"text": "shortcut response"}`')
    expect(chat_input).to_have_text('fake_claude:text `{"text": "shortcut response"}`')
    # Wait for React to re-render so promptDraft atom is updated
    wait_for_one_frame(page)

    # Press modifier+Shift+Enter to interrupt and send.
    # handleInterruptAndSend calls sendMessage() then interruptWorkspaceAgent()
    # asynchronously — Playwright returns from the keypress immediately.
    modifier = get_playwright_modifier_key()
    chat_input.press(f"{modifier}+Shift+Enter")

    # No queued message bar should appear — shortcut sends immediately
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    # The interrupted sleep + user message + agent response = 3 messages.
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)


@user_story("to interrupt the agent and send a queued message via global keyboard shortcut")
def test_keyboard_shortcut_interrupt_and_send_queued_message(sculptor_instance_: SculptorInstance) -> None:
    """Meta+Shift+Enter sends a queued message immediately even when chat input is disabled."""
    _, chat_panel = _start_busy_agent(sculptor_instance_)
    page = chat_panel._page

    # Queue a message while agent is busy
    send_chat_message(chat_panel=chat_panel, message='fake_claude:text `{"text": "queued response"}`')
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Chat input send button should be disabled (message is queued)
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_disabled()

    # Press modifier+Shift+Enter globally — should interrupt and send the queued message
    modifier = get_playwright_modifier_key()
    page.keyboard.press(f"{modifier}+Shift+Enter")

    # Queued message bar should disappear
    expect(chat_panel.get_queued_message_bar()).to_have_count(0)

    # Agent should eventually finish processing the promoted message.
    # The interrupted fake_claude:sleep produces no visible text, so we get
    # 3 messages: user1 (sleep) + user2 (promoted) + assistant2 (response).
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=3)


@user_story("to keep a queued message queued when the agent pauses on an ask-question panel")
def test_queued_message_stays_queued_when_ask_user_question_appears(sculptor_instance_: SculptorInstance) -> None:
    """A message queued while the agent is running must STAY queued when the
    agent then pauses on an AskUserQuestion panel.

    Regression (SCU-1319): when the AUQ panel appears, the task's derived
    status flips from RUNNING to WAITING (see web/derived.py:_ready_or_waiting).
    AlphaChatInterface computed ``isAgentBusy`` from RUNNING alone, so the moment
    the question appeared the queued message was flushed into
    ``effectiveChatMessages`` and rendered as an already-sent user message — and
    the queued-message bar vanished. The fix keeps queued messages queued while a
    question is pending.
    """
    page = sculptor_instance_.page

    # Queuing only happens when always-interrupt-and-send is OFF; with it ON a
    # sent message interrupts the agent instead of queuing. A sibling test in
    # this file enables it on the shared instance and does not reset it, so
    # disable it defensively before we start (same guard as
    # test_always_interrupt_setting_does_not_affect_existing_queued_message).
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.disable_always_interrupt()
    page.go_back()

    # One agent turn with two steps: first block on a sentinel file (keeping the
    # agent busy so we can queue a message — no wall-clock, per the integration
    # test review rules), then ask a question (which flips the task to WAITING).
    pause = FakeClaudePause()
    prompt = f"""\
fake_claude:multi_step `{{
  "steps": [
    {{"command": "wait_for_file", "args": {{"path": "{pause.release_path}"}}}},
    {{
      "command": "ask_user_question",
      "args": {{
        "questions": [
          {{
            "question": "What language do you prefer?",
            "header": "Language",
            "options": [
              {{"label": "Python", "description": "A versatile language"}},
              {{"label": "Rust", "description": "For systems programming"}}
            ],
            "multiSelect": false
          }}
        ]
      }}
    }}
  ]
}}`"""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=prompt,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Queue a message while the agent is busy (blocked on the sentinel file).
    send_chat_message(chat_panel=chat_panel, message="queued while running")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    # Release the agent: it proceeds to the ask-question step and the AUQ panel
    # appears, flipping the task status to WAITING.
    pause.release()
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)

    # The queued message must STILL be queued — not promoted into the chat as a
    # sent message. With the bug the bar count drops to 0 here.
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    expect(chat_panel.get_queued_message_bar()).to_contain_text("queued while running")
