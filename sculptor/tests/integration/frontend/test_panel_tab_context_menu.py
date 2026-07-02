"""Integration tests for the shared panel-tab context menu.

The redesigned shell renders ONE context menu for every panel tab (agent and
terminal alike): Rename for multi-instance panels, plus — for agents —
"Mark as unread" and the flat diagnostics copy items (copy
agent id / name, copy claude session id / transcript paths, disabled until a
session exists). Closing a tab routes through the close (X) button to a
confirmation dialog. Close-others is not part of the
panel-tab context menu (only Rename, Mark as unread, and the diagnostics copy
items render).

These cases consolidate the retired `test_agent_tab_context_menu.py`,
`test_agent_diagnostics_context_menu.py`, and the rename/context halves of
`test_terminal_tab_enhancements.py` / `test_tab_context_menus.py` onto the
panel-tab model.

Diagnostics is a FLAT set of copy items (no "Diagnostics" sub-menu), so items —
like "Mark as unread" — are asserted by their visible label rather than a
per-item testid.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

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
    # The inline rename input is dismissed on commit (the persisted label change is
    # wired to the data layer in a later task; here we assert the affordance works).
    expect(panel_tabs.get_inline_rename_input()).not_to_be_visible()


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

    terminal_tab = bottom_tabs.get_active_tab()
    expect(terminal_tab).to_be_visible()
    terminal_tab.dblclick()
    expect(bottom_tabs.get_inline_rename_input()).to_be_visible()


def _copy_via_context_menu(page: Page, panel_tabs: PlaywrightPanelTabElement, tab: Locator, label: str) -> str:
    """Open ``tab``'s context menu, click the copy item named ``label``, and
    return the intercepted clipboard text.

    Each click closes the menu, so callers invoke this once per item. The
    session-dependent items render disabled (Radix ``data-disabled``) until the
    agent's diagnostics load — and menu items resolve their state when the menu
    OPENS, so an already-open menu never flips to enabled in place. Reopen the
    menu until the item is enabled instead of polling one open menu.
    """
    item = panel_tabs.get_diagnostics_item_by_text(label)
    for _ in range(15):
        panel_tabs.open_context_menu(tab)
        expect(item).to_be_visible()
        try:
            expect(item).not_to_have_attribute("data-disabled", "", timeout=2_000)
            break
        except AssertionError:
            page.keyboard.press("Escape")
            expect(item).not_to_be_visible()
    else:
        raise AssertionError(f"{label!r} stayed disabled — the agent's diagnostics never loaded")
    reset_intercepted_clipboard(page)
    item.click()
    page.wait_for_function("() => window.__clipboardWritten !== null")
    copied = read_intercepted_clipboard(page)
    assert copied is not None, f"Expected {label!r} to write to the clipboard"
    return copied


@user_story("to copy an agent's id from its tab context menu")
def test_agent_tab_copy_agent_id(sculptor_instance_: SculptorInstance) -> None:
    """The agent tab context menu copies the agent id (always available, no session needed)."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    task_page = start_task_and_wait_for_ready(page, prompt="Copy id agent", workspace_name="Copy Id WS")
    install_clipboard_interceptor(page)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    # The copied value is the agent's task id — the same id the agent page URL carries.
    agent_id = _copy_via_context_menu(page, panel_tabs, tabs.first, "Copy agent id")
    assert agent_id == task_page.get_task_id(), (
        f"Expected the copied agent id to match the URL's task id; got {agent_id!r} vs {task_page.get_task_id()!r}"
    )


@user_story("to copy an agent's name, session id, and transcript paths from its tab context menu")
def test_agent_tab_diagnostics_copy_contents(sculptor_instance_: SculptorInstance) -> None:
    """The diagnostics copy items copy real values once the agent has a session.

    After a completed run: "Copy agent name" copies the tab's display name,
    "Copy claude session id" copies a non-empty id, "Copy claude transcript file
    path" copies that session's ``.jsonl`` path, and "Copy Sculptor transcript
    file path" copies the task's ``transcript.jsonl`` artifact path.
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    task_page = start_task_and_wait_for_ready(page, prompt="Diagnostics copy agent", workspace_name="Diag Copy WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    install_clipboard_interceptor(page)

    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    agent_name = _copy_via_context_menu(page, panel_tabs, tabs.first, "Copy agent name")
    assert agent_name, "Expected a non-empty agent name"
    expect(tabs.first).to_contain_text(agent_name)

    session_id = _copy_via_context_menu(page, panel_tabs, tabs.first, "Copy claude session id")
    assert session_id, "Expected a non-empty claude session id"

    transcript_path = _copy_via_context_menu(page, panel_tabs, tabs.first, "Copy claude transcript file path")
    assert transcript_path.endswith(".jsonl"), f"Expected a.jsonl transcript path, got {transcript_path!r}"
    assert session_id in transcript_path, (
        f"Expected the transcript path to be the session's jsonl; got {transcript_path!r} for session {session_id!r}"
    )

    sculptor_transcript_path = _copy_via_context_menu(
        page, panel_tabs, tabs.first, "Copy Sculptor transcript file path"
    )
    assert sculptor_transcript_path.endswith("transcript.jsonl"), (
        f"Expected the task's transcript.jsonl artifact path, got {sculptor_transcript_path!r}"
    )


@user_story("to see diagnostics copy items disabled for an agent with no session")
def test_agent_tab_diagnostics_disabled_without_session(sculptor_instance_: SculptorInstance) -> None:
    """The session/transcript copy items are disabled for an agent that has not run.

    A freshly-added second agent has no session yet, so "Copy claude session id" is
    disabled (Radix marks disabled items with ``data-disabled``).
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Has session", workspace_name="Diag Disabled WS")
    # The second agent has no session yet.
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_tabs.open_context_menu(tabs.nth(1))
    copy_session_id = panel_tabs.get_diagnostics_item_by_text("Copy claude session id")
    expect(copy_session_id).to_be_visible()
    expect(copy_session_id).to_have_attribute("data-disabled", "")


@user_story("to close an agent from its tab with a confirmation")
def test_agent_tab_close_requires_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Closing an agent panel tab surfaces the delete confirmation."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Close confirm agent", workspace_name="Close Confirm Menu WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    second_tab = tabs.nth(1)
    testid = second_tab.get_attribute("data-testid")
    assert testid is not None and testid.startswith("PANEL_TAB-")
    panel_id = testid[len("PANEL_TAB-") :]

    second_tab.click()
    panel_tabs.get_tab_close_button(panel_id).click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_visible()
    panel_tabs.get_delete_confirmation_confirm_button().click()
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()
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
