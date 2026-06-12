"""Integration tests for the /btw side-chat feature."""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import clear_tiptap
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.btw_popup import get_btw_popup
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_BTW_ANSWER_PROMPT = 'fake_claude:text `{"text": "Here is a side-chat answer."}`'


def _submit_btw(chat_panel, question: str) -> None:
    """Type `/btw <question>` into the chat input and dispatch the SendButton click.

    Uses ``dispatch_event("click")`` rather than ``click()`` because a previous
    /btw may have left the popup visible in the bottom-right of the chat panel,
    overlapping the SendButton. ``dispatch_event`` fires the React onClick
    directly on the button, bypassing the pointer-event chain that the popup
    would otherwise intercept.
    """
    chat_input = chat_panel.get_chat_input()
    clear_tiptap(chat_input)
    type_into_tiptap(chat_panel._page, chat_input, f"/btw {question}")
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.dispatch_event("click")


@user_story("to ask /btw while main is busy and see an answer streamed into the popup")
def test_btw_happy_path_while_main_busy(sculptor_instance_: SculptorInstance) -> None:
    """T1: full roundtrip — type /btw while main is RUNNING, see popup with answer."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:sleep `{"seconds": 30}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    _submit_btw(chat_panel, _BTW_ANSWER_PROMPT)

    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup.get_question()).to_contain_text("fake_claude:text", timeout=60_000)
    expect(popup.get_answer()).to_contain_text("Here is a side-chat answer.", timeout=60_000)

    popup.get_close_button().click()
    expect(popup).not_to_be_visible()


@user_story("to replace the popup contents with a second /btw")
def test_btw_replaces_in_place(sculptor_instance_: SculptorInstance) -> None:
    """T2: firing a second /btw replaces the popup's contents."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:sleep `{"seconds": 30}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "answer one"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup.get_answer()).to_contain_text("answer one", timeout=60_000)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "answer two"}`')
    expect(popup.get_answer()).to_contain_text("answer two", timeout=60_000)
    expect(popup.get_question()).to_contain_text("answer two")


@user_story("to have /btw bypass the busy-queue lock on the SendButton")
def test_btw_bypasses_busy_lock(sculptor_instance_: SculptorInstance) -> None:
    """T3: when a queued message exists, regular text keeps Send disabled but /btw enables it."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:sleep `{"seconds": 30}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Queue a regular message while main is busy — this flips isDisabled=true.
    send_chat_message(chat_panel=chat_panel, message="queued regular message")
    expect(chat_panel.get_queued_message_bar()).to_have_count(1)

    chat_input = chat_panel.get_chat_input()
    send_button = chat_panel.get_send_button()

    # Regular text keeps the button disabled.
    clear_tiptap(chat_input)
    type_into_tiptap(sculptor_instance_.page, chat_input, "plain text message")
    expect(send_button).to_be_disabled()

    # Replacing the draft with /btw <text> re-enables Send despite the lock.
    clear_tiptap(chat_input)
    type_into_tiptap(sculptor_instance_.page, chat_input, f"/btw {_BTW_ANSWER_PROMPT}")
    expect(send_button).to_be_enabled()


@user_story("to keep the popup unchanged when main finishes its turn")
def test_btw_popup_unchanged_when_main_goes_ready(sculptor_instance_: SculptorInstance) -> None:
    """T4: main flipping RUNNING → READY leaves the popup visible with the same content."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "soak answer"}`')

    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup.get_answer()).to_contain_text("soak answer", timeout=60_000)

    # Main is idle — the popup stays put with its content.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(popup).to_be_visible()
    expect(popup.get_answer()).to_contain_text("soak answer")


@user_story("to lose the /btw popup on page refresh")
def test_btw_popup_clears_on_refresh(sculptor_instance_: SculptorInstance) -> None:
    """T5: the popup is in-memory only — a reload destroys it."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "ephemeral"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup).to_be_visible(timeout=60_000)

    # Hard reload so Jotai's in-memory atoms are fully reset (soft_reload_page
    # re-navigates to the same URL but dev-mode module caches can keep stale
    # subscriptions alive briefly, producing a visible flash of the popup).
    sculptor_instance_.page.reload(wait_until="networkidle")

    chat_panel_locator = sculptor_instance_.page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel_locator).to_be_visible(timeout=60_000)
    expect(get_btw_popup(sculptor_instance_.page)).not_to_be_visible()


@user_story("to see an inline hint when submitting a bare /btw")
def test_btw_empty_shows_inline_toast(sculptor_instance_: SculptorInstance) -> None:
    """T6: bare /btw rejects with an inline toast and does not open the popup."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    chat_input = chat_panel.get_chat_input()
    type_into_tiptap(sculptor_instance_.page, chat_input, "/btw")
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()

    toast = sculptor_instance_.page.get_by_test_id(ElementIDs.TOAST)
    expect(toast).to_contain_text("Type a question after /btw")
    expect(get_btw_popup(sculptor_instance_.page)).not_to_be_visible()


@user_story("to see a toast when /btw is the first message in a fresh workspace")
def test_btw_first_message_shows_unavailable_toast(sculptor_instance_: SculptorInstance) -> None:
    """First-message-is-/btw: a fresh workspace has no main-agent session
    to fork from. The backend fast-fails with 409 and the frontend toasts
    that /btw is unavailable until the user has sent a regular message."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="",
    )
    chat_panel = task_page.get_chat_panel()

    _submit_btw(chat_panel, _BTW_ANSWER_PROMPT)

    toast = sculptor_instance_.page.get_by_test_id(ElementIDs.TOAST)
    expect(toast).to_contain_text("/btw is unavailable until you've sent a message")
    expect(get_btw_popup(sculptor_instance_.page)).not_to_be_visible()


@user_story("to dismiss the /btw popup with the Escape key")
def test_btw_popup_closes_on_escape(sculptor_instance_: SculptorInstance) -> None:
    """Escape is a dismissal shortcut alongside the × button."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "esc closes"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup.get_answer()).to_contain_text("esc closes", timeout=60_000)

    sculptor_instance_.page.keyboard.press("Escape")
    expect(popup).not_to_be_visible()


@user_story("to keep the /btw popup open when clicking outside it")
def test_btw_popup_ignores_outside_click(sculptor_instance_: SculptorInstance) -> None:
    """Click-outside is inert — only × and Esc dismiss the popup."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "still open"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup.get_answer()).to_contain_text("still open", timeout=60_000)

    # Click outside the popup (on the chat panel background).
    chat_panel_locator = sculptor_instance_.page.get_by_test_id(ElementIDs.CHAT_PANEL)
    chat_panel_locator.click(position={"x": 10, "y": 10})
    expect(popup).to_be_visible()


@user_story("to land focus inside the /btw popup as soon as it opens")
def test_btw_popup_takes_focus_on_open(sculptor_instance_: SculptorInstance) -> None:
    """Opening the popup moves keyboard focus into it so Esc and Tab work."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "focus test"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup).to_be_visible(timeout=60_000)
    # The popup container itself receives focus on mount.
    expect(popup).to_be_focused()


@user_story("to land focus back in the prompt input when the /btw popup closes")
def test_btw_popup_restores_focus_to_chat_input_on_close(sculptor_instance_: SculptorInstance) -> None:
    """× and Esc both return keyboard focus to the chat input."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "focus restore"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup).to_be_focused()

    popup.get_close_button().click()
    expect(popup).not_to_be_visible()

    # The TipTap chat input is a contenteditable inside the chat-input container.
    chat_input_editable = chat_panel.get_chat_input()
    expect(chat_input_editable).to_be_focused()


@user_story("to keep the main agent running when /btw fires while always-interrupt-and-send is on")
def test_btw_does_not_interrupt_main_with_always_interrupt_and_send(
    sculptor_instance_: SculptorInstance,
) -> None:
    """B1: /btw must never trigger interruptWorkspaceAgent on the main agent.

    When the user has the experimental "Always interrupt and send" setting on,
    submitting any non-pseudo-skill draft while main is RUNNING fires an
    InterruptProcessUserMessage right after the message is sent. /btw bypasses
    the busy-state lock to dispatch its own subprocess but must NOT trigger
    that interrupt — /btw is "never forwarded to main."
    """
    page = sculptor_instance_.page

    # Enable always-interrupt via the settings UI so the server persists the
    # setting and the frontend picks it up on subsequent navigations.
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_always_interrupt()

    # Start a long-sleeping main agent. With the bug, firing /btw will
    # interrupt this sleep and the agent will stop running before the sleep
    # completes; without the bug, the sleep continues for its full duration.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:sleep `{"seconds": 30}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    _submit_btw(chat_panel, _BTW_ANSWER_PROMPT)

    # The popup must appear (proves the /btw HTTP call was dispatched).
    popup = get_btw_popup(page)
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup.get_answer()).to_contain_text("Here is a side-chat answer.", timeout=60_000)

    # Wait long enough for any interrupt chain (frontend → backend → SIGTERM →
    # FakeClaude exit → agent state flip) to settle. Existing
    # test_always_interrupt_setting_bypasses_queue uses 3000ms; we use 5000ms
    # to add headroom against test-runner jitter.
    page.wait_for_timeout(5000)

    # The thinking indicator must still be visible — main is still sleeping.
    # If /btw had triggered interruptWorkspaceAgent, the sleep would have been
    # terminated, the indicator would be gone, and a stopped/error message
    # would already be in the chat.
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # Reset always-interrupt before returning to the shared sculptor_instance_
    # so later tests in the same session see the default OFF state.
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.disable_always_interrupt()


@user_story("to drag the /btw popup to a new position on the chat panel")
def test_btw_popup_is_draggable(sculptor_instance_: SculptorInstance) -> None:
    """T8: dragging the title bar moves the popup's bounding box."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "drag me"}`')
    popup = get_btw_popup(sculptor_instance_.page)
    expect(popup).to_be_visible(timeout=60_000)

    drag_handle = popup.get_drag_handle()
    drag_handle.hover()
    start_box = drag_handle.bounding_box()
    assert start_box is not None
    initial_popup_box = popup.bounding_box()
    assert initial_popup_box is not None

    target_x = start_box["x"] - 80
    target_y = start_box["y"] - 60
    sculptor_instance_.page.mouse.down()
    sculptor_instance_.page.mouse.move(target_x, target_y, steps=10)
    sculptor_instance_.page.mouse.up()

    moved_popup_box = popup.bounding_box()
    assert moved_popup_box is not None
    assert abs(moved_popup_box["x"] - initial_popup_box["x"]) > 10
    assert abs(moved_popup_box["y"] - initial_popup_box["y"]) > 10


@user_story("to see the /btw popup return to its default position after close + reopen")
def test_btw_popup_position_resets_after_close(sculptor_instance_: SculptorInstance) -> None:
    """B3: a fresh /btw after × must open at the default bottom-right inset.

    Architecture §4.3: drag position is preserved on in-place replace
    but must NOT persist across close → reopen cycles. The popup
    component holds drag offsets in local React state that survives the
    "closed" render path, so without the fix the second popup appears at
    the previous drag-to position instead of the default anchor.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    # Open the first popup and record its default position.
    _submit_btw(chat_panel, 'fake_claude:text `{"text": "first popup"}`')
    popup = get_btw_popup(page)
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup.get_answer()).to_contain_text("first popup", timeout=60_000)

    default_box = popup.bounding_box()
    assert default_box is not None

    # Drag it well away from the default position.
    drag_handle = popup.get_drag_handle()
    drag_handle.hover()
    handle_box = drag_handle.bounding_box()
    assert handle_box is not None
    page.mouse.down()
    page.mouse.move(handle_box["x"] - 120, handle_box["y"] - 90, steps=10)
    page.mouse.up()

    moved_box = popup.bounding_box()
    assert moved_box is not None
    # Sanity check: the drag actually moved the popup. If this fails the
    # test setup itself is wrong, not the bug we're guarding against.
    assert abs(moved_box["x"] - default_box["x"]) > 20
    assert abs(moved_box["y"] - default_box["y"]) > 20

    # Close via ×.
    popup.get_close_button().click()
    expect(popup).not_to_be_visible()

    # Open a fresh popup. With the bug, the dragged position is reused.
    _submit_btw(chat_panel, 'fake_claude:text `{"text": "second popup"}`')
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup.get_answer()).to_contain_text("second popup", timeout=60_000)

    reopened_box = popup.bounding_box()
    assert reopened_box is not None
    # The reopened popup must be at (or very near) the default anchor, NOT
    # at the dragged-to position. A few pixels of layout jitter is fine,
    # so allow up to 10px slop on each axis.
    assert abs(reopened_box["x"] - default_box["x"]) <= 10, (
        f"reopened popup x={reopened_box['x']:.1f} should be close to default x={default_box['x']:.1f}"
        + f" but is closer to dragged x={moved_box['x']:.1f} — localPosition leaked across close+reopen."
    )
    assert abs(reopened_box["y"] - default_box["y"]) <= 10, (
        f"reopened popup y={reopened_box['y']:.1f} should be close to default y={default_box['y']:.1f}"
        + f" but is closer to dragged y={moved_box['y']:.1f} — localPosition leaked across close+reopen."
    )


@user_story("to dismiss the /btw popup when switching to a different agent tab")
def test_btw_popup_dismisses_on_agent_tab_switch(sculptor_instance_: SculptorInstance) -> None:
    """B4: a /btw popup belongs to the agent it was opened in.

    Each /btw question is forked from one specific agent's session. As soon as
    the user navigates to a different agent (different tab in the same
    workspace), the popup is no longer relevant and must be dismissed —
    otherwise the user sees an answer about Agent A's context floating over
    Agent B's chat panel.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "agent A answer"}`')
    popup = get_btw_popup(page)
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup.get_answer()).to_contain_text("agent A answer", timeout=60_000)

    # Add a second agent in the same workspace and switch to it.
    add_agent_button = page.get_by_test_id(ElementIDs.ADD_AGENT_BUTTON)
    add_agent_button.click()
    agent_tabs = page.get_by_test_id(ElementIDs.AGENT_TAB)
    expect(agent_tabs).to_have_count(2, timeout=30_000)

    # The popup must disappear: it belonged to agent A and we're now on agent B.
    expect(popup).not_to_be_visible()


@user_story("to dismiss the /btw popup when switching to a different workspace")
def test_btw_popup_dismisses_on_workspace_switch(sculptor_instance_: SculptorInstance) -> None:
    """B4: a /btw popup is tied to one agent in one workspace.

    Switching workspaces puts the user in front of an entirely different
    agent (and chat). The popup, which carries an answer scoped to the
    previous agent's session, must be dismissed.
    """
    page = sculptor_instance_.page

    # First workspace + agent + popup.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
        workspace_name="WS One",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, 2)

    _submit_btw(chat_panel, 'fake_claude:text `{"text": "ws-one answer"}`')
    popup = get_btw_popup(page)
    expect(popup).to_be_visible(timeout=60_000)
    expect(popup.get_answer()).to_contain_text("ws-one answer", timeout=60_000)

    # Create a second workspace and navigate to it via the same UI flow.
    # `start_task_and_wait_for_ready` waits for the new workspace's chat
    # panel to be visible before returning, so by the next line we are
    # demonstrably looking at workspace two.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"{_BTW_ANSWER_PROMPT}",
        workspace_name="WS Two",
    )

    # The popup must be gone: we're now in a different workspace looking at
    # a different agent. The atom carrying ws-one's question/answer must
    # not bleed across.
    expect(popup).not_to_be_visible()
