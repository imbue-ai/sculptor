"""Integration tests for the shared panel-tab context menu.

The redesigned shell renders ONE context menu for every panel tab (agent and
terminal alike), with a clear hierarchy: Rename, then the agent's own actions
(Mark as unread, Copy agent name, and a ``Diagnostics`` submenu grouping the id /
session id / transcript-path copy items), then the section split options, then a
destructive row — ``Delete`` for agents, ``Close`` for terminals.

Every actionable row carries a ``TAB_CONTEXT_MENU_*`` testid. The id / session /
transcript copy items sit behind the Diagnostics submenu (opened by hovering its
trigger) and render disabled (Radix ``data-disabled``) until their value exists.
Closing a tab routes through either the always-visible X button or the menu's
destructive row; both surface the same confirmation dialog.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.clipboard import reset_intercepted_clipboard
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to rename an agent panel tab but not close it via a dedicated menu item")
def test_agent_tab_offers_rename(sculptor_instance_: SculptorInstance) -> None:
    """An agent panel tab's context menu offers Rename and starts an inline edit."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Rename menu agent", workspace_name="Rename Menu WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_tabs.rename_tab_via_context_menu(tabs.nth(1), "Renamed Agent")
    expect(tabs.nth(1)).to_contain_text("Renamed Agent")


@user_story("to rename a terminal panel tab via double-click")
def test_terminal_tab_double_click_rename(sculptor_instance_: SculptorInstance) -> None:
    """Double-clicking a terminal panel tab starts an inline rename."""
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Rename WS")
    # Create a terminal in the bottom section and rename the one we just created (it is
    # the active tab). Renaming the active tab keeps this independent of terminal label
    # numbering — the default layout already seeds a terminal in the bottom section.
    create_terminal_panel(page, section="bottom")
    expect(bottom_tabs.get_panel_tabs()).to_have_count(2)

    terminal_tab = bottom_tabs.get_active_tab()
    expect(terminal_tab).to_be_visible()
    # Double-clicking starts the inline rename. The gesture is retried because a native
    # double-click can be dropped under heavy main-thread contention (see the POM).
    expect(bottom_tabs.start_inline_rename_via_double_click(terminal_tab)).to_be_visible()


def _copy_top_level_item(page: Page, panel_tabs: PlaywrightPanelTabElement, tab: Locator, test_id: str) -> str:
    """Open ``tab``'s context menu, click the top-level copy item identified by
    ``test_id``, and return the intercepted clipboard text."""
    panel_tabs.open_context_menu(tab)
    item = panel_tabs.get_menu_item(test_id)
    expect(item).to_be_visible()
    reset_intercepted_clipboard(page)
    item.click()
    page.wait_for_function("() => window.__clipboardWritten !== null")
    copied = read_intercepted_clipboard(page)
    assert copied is not None, f"Expected {test_id!r} to write to the clipboard"
    return copied


def _copy_diagnostics_item(page: Page, panel_tabs: PlaywrightPanelTabElement, tab: Locator, test_id: str) -> str:
    """Open ``tab``'s Diagnostics submenu, click the copy item identified by
    ``test_id``, and return the intercepted clipboard text.

    Session-dependent items render disabled (Radix ``data-disabled``) until the
    agent's diagnostics load — and menu items resolve their state when the menu
    OPENS, so an already-open menu never flips to enabled in place. Reopen the menu
    (re-hovering Diagnostics) until the item is enabled instead of polling one open
    menu.
    """
    item = panel_tabs.get_menu_item(test_id)
    for _ in range(15):
        panel_tabs.open_diagnostics_submenu(tab)
        expect(item).to_be_visible()
        try:
            expect(item).not_to_have_attribute("data-disabled", "", timeout=2_000)
            break
        except AssertionError:
            # Close the submenu and its root menu, then retry a fresh open.
            page.keyboard.press("Escape")
            page.keyboard.press("Escape")
            expect(item).not_to_be_visible()
    else:
        raise AssertionError(f"{test_id!r} stayed disabled — the agent's diagnostics never loaded")
    reset_intercepted_clipboard(page)
    item.click()
    page.wait_for_function("() => window.__clipboardWritten !== null")
    copied = read_intercepted_clipboard(page)
    assert copied is not None, f"Expected {test_id!r} to write to the clipboard"
    return copied


@user_story("to copy an agent's id from its tab context menu")
def test_agent_tab_copy_agent_id(sculptor_instance_: SculptorInstance) -> None:
    """The Diagnostics submenu copies the agent id (always available, no session needed)."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    task_page = start_task_and_wait_for_ready(page, prompt="Copy id agent", workspace_name="Copy Id WS")
    install_clipboard_interceptor(page)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    # The copied value is the agent's task id — the same id the agent page URL carries.
    agent_id = _copy_diagnostics_item(page, panel_tabs, tabs.first, ElementIDs.TAB_CONTEXT_MENU_COPY_AGENT_ID)
    assert agent_id == task_page.get_task_id(), (
        f"Expected the copied agent id to match the URL's task id; got {agent_id!r} vs {task_page.get_task_id()!r}"
    )


@user_story("to copy an agent's name, session id, and transcript paths from its tab context menu")
def test_agent_tab_diagnostics_copy_contents(sculptor_instance_: SculptorInstance) -> None:
    """The copy items copy real values once the agent has a session.

    After a completed run: "Copy agent name" (top level) copies the tab's display
    name, and inside Diagnostics "Copy claude session id" copies a non-empty id,
    "Copy claude transcript file path" copies that session's ``.jsonl`` path, and
    "Copy Sculptor transcript file path" copies the task's ``transcript.jsonl``
    artifact path.
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    task_page = start_task_and_wait_for_ready(page, prompt="Diagnostics copy agent", workspace_name="Diag Copy WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    install_clipboard_interceptor(page)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    # Copy agent name is a top-level action (always available).
    agent_name = _copy_top_level_item(page, panel_tabs, tabs.first, ElementIDs.TAB_CONTEXT_MENU_COPY_AGENT_NAME)
    assert agent_name, "Expected a non-empty agent name"
    expect(tabs.first).to_contain_text(agent_name)

    # Session id + transcript paths live in the Diagnostics submenu, enabled once a session exists.
    session_id = _copy_diagnostics_item(
        page, panel_tabs, tabs.first, ElementIDs.TAB_CONTEXT_MENU_COPY_CLAUDE_SESSION_ID
    )
    assert session_id, "Expected a non-empty claude session id"

    transcript_path = _copy_diagnostics_item(
        page, panel_tabs, tabs.first, ElementIDs.TAB_CONTEXT_MENU_COPY_CLAUDE_TRANSCRIPT_PATH
    )
    assert transcript_path.endswith(".jsonl"), f"Expected a .jsonl transcript path, got {transcript_path!r}"
    assert session_id in transcript_path, (
        f"Expected the transcript path to be the session's jsonl; got {transcript_path!r} for session {session_id!r}"
    )

    sculptor_transcript_path = _copy_diagnostics_item(
        page, panel_tabs, tabs.first, ElementIDs.TAB_CONTEXT_MENU_COPY_SCULPTOR_TRANSCRIPT_PATH
    )
    assert sculptor_transcript_path.endswith("transcript.jsonl"), (
        f"Expected the task's transcript.jsonl artifact path, got {sculptor_transcript_path!r}"
    )


@user_story("to see diagnostics copy items disabled for an agent with no session")
def test_agent_tab_diagnostics_disabled_without_session(sculptor_instance_: SculptorInstance) -> None:
    """The session/transcript copy items are disabled for an agent that has not run.

    A freshly-added second agent has no session yet, so — inside the Diagnostics
    submenu — "Copy claude session id" is disabled (Radix marks disabled items with
    ``data-disabled``).
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Has session", workspace_name="Diag Disabled WS")
    # The second agent has no session yet.
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_tabs.open_diagnostics_submenu(tabs.nth(1))
    copy_session_id = panel_tabs.get_menu_item(ElementIDs.TAB_CONTEXT_MENU_COPY_CLAUDE_SESSION_ID)
    expect(copy_session_id).to_be_visible()
    expect(copy_session_id).to_have_attribute("data-disabled", "")


@user_story("to close an agent from its tab with a confirmation")
def test_agent_tab_close_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing an agent panel tab via the X button surfaces the delete confirmation."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Close confirm agent", workspace_name="Close Confirm Menu WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    second_tab = tabs.nth(1)
    second_tab.click()
    panel_tabs.get_tab_close_button_of(second_tab).click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_visible()
    panel_tabs.get_delete_confirmation_confirm_button().click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(tabs).to_have_count(1)


@user_story("to delete an agent from its tab context menu's destructive row")
def test_agent_tab_delete_from_context_menu(sculptor_instance_: SculptorInstance) -> None:
    """The agent tab context menu's destructive Delete row opens the delete confirmation."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Delete menu agent", workspace_name="Delete Menu WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_tabs.open_context_menu(tabs.nth(1))
    delete_item = panel_tabs.get_context_menu_delete_item()
    expect(delete_item).to_be_visible()
    delete_item.click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_visible()
    panel_tabs.get_delete_confirmation_confirm_button().click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(tabs).to_have_count(1)


@user_story("to close a terminal from its tab context menu's destructive row")
def test_terminal_tab_close_from_context_menu(sculptor_instance_: SculptorInstance) -> None:
    """The terminal tab context menu's destructive Close row opens the close confirmation."""
    page = sculptor_instance_.page
    bottom_tabs = PlaywrightPanelTabElement(page, sub_section="bottom")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Terminal Close Menu WS")
    # The default layout seeds a terminal in the bottom section; create another and close
    # the one we just made (the active tab), keeping this independent of label numbering.
    create_terminal_panel(page, section="bottom")
    tabs = bottom_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    terminal_tab = bottom_tabs.get_active_tab()
    bottom_tabs.open_context_menu(terminal_tab)
    close_item = bottom_tabs.get_context_menu_close_item()
    expect(close_item).to_be_visible()
    close_item.click()
    # Terminals are "closed" (they hold no durable history), so the same confirmation
    # dialog appears titled "Close terminal?".
    expect(bottom_tabs.get_delete_confirmation_dialog()).to_be_visible()
    bottom_tabs.get_delete_confirmation_confirm_button().click()
    expect(bottom_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(tabs).to_have_count(1)


@user_story("to mark an agent unread from its tab context menu")
def test_agent_tab_mark_unread(sculptor_instance_: SculptorInstance) -> None:
    """The agent tab context menu offers "Mark as unread", and clicking it flips the
    tab's ``data-dot-status`` to unread.

    Marking the currently viewed agent unread is allowed — the unread
    override suppresses the auto mark-read, so the dot must not revert.
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    task_page = start_task_and_wait_for_ready(page, prompt="Mark unread agent", workspace_name="Mark Unread Menu WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)
    expect(tabs.first).to_have_attribute("data-dot-status", "read")

    panel_tabs.open_context_menu(tabs.first)
    mark_unread_item = panel_tabs.get_context_menu_mark_unread_item()
    expect(mark_unread_item).to_be_visible()
    mark_unread_item.click()

    expect(tabs.first).to_have_attribute("data-dot-status", "unread")
