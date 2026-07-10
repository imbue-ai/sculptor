"""Integration tests for single-instance panel rename/close.

This file owns the SINGLE-INSTANCE (static) panel half of the tab rename/close
behaviour: a static panel (e.g. Files) cannot be renamed — its context menu has no
Rename item and double-clicking it does not start an inline edit — and closing it
simply removes it from the section header (no confirmation, since there is no
underlying entity to delete).

The multi-instance (agent/terminal) rename-via-context-menu / double-click and
close=delete cases are owned by ``test_panel_tab_context_menu.py`` and
``test_agent_panel.py``; they are NOT duplicated here.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.section_split import PlaywrightSectionSplit
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to not be offered a rename for a single-instance panel tab")
def test_static_panel_tab_has_no_rename_in_context_menu(sculptor_instance_: SculptorInstance) -> None:
    """A single-instance (Files) panel tab's context menu offers NO Rename item."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Static No Rename WS")

    # Files is seeded into the left section, so open_panel reveals it there;
    # the tab and its affordances live in the left header.
    left = PlaywrightWorkspaceSection(page, "left")
    open_panel(page, "files", "left")
    files_tab = left.get_panel_tab("files")
    expect(files_tab).to_be_visible()

    panel_tabs = PlaywrightPanelTabElement(page, sub_section="left")
    panel_tabs.open_context_menu(files_tab)
    # Anchor on an item the menu DOES offer before asserting Rename's absence: the
    # unsplit left section always offers "Create split and move panel", so waiting on it
    # confirms the menu actually opened (otherwise a swallowed right-click would make
    # the negative assertion pass vacuously).
    expect(PlaywrightSectionSplit(page, "left").get_create_option("horizontal")).to_be_visible()
    # No Rename item is offered for a single-instance panel.
    expect(panel_tabs.get_context_menu_rename_item()).to_have_count(0)
    # Dismiss the context menu.
    page.keyboard.press("Escape")


@user_story("to not start an inline rename when I double-click a single-instance panel tab")
def test_static_panel_tab_double_click_does_not_rename(sculptor_instance_: SculptorInstance) -> None:
    """Double-clicking a single-instance (Files) panel tab does NOT start an inline rename."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Static No Dblclick WS")

    # Files is seeded into the left section, so open_panel reveals it there.
    left = PlaywrightWorkspaceSection(page, "left")
    open_panel(page, "files", "left")
    files_tab = left.get_panel_tab("files")
    expect(files_tab).to_be_visible()

    panel_tabs = PlaywrightPanelTabElement(page, sub_section="left")
    files_tab.dblclick()
    # No inline rename input appears for a single-instance panel.
    expect(panel_tabs.get_inline_rename_input()).to_have_count(0)


@user_story("to close a single-instance panel and remove it from the header")
def test_static_panel_close_removes_it_from_header(sculptor_instance_: SculptorInstance) -> None:
    """Closing a single-instance (Files) panel removes its tab with no confirmation."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Static Close WS")

    # Files is seeded into the left section, so open_panel reveals it there.
    left = PlaywrightWorkspaceSection(page, "left")
    open_panel(page, "files", "left")
    expect(left.get_panel_tab("files")).to_be_visible()

    panel_tabs = PlaywrightPanelTabElement(page, sub_section="left")
    panel_tabs.get_tab_close_button("files").click()

    # The static panel closes immediately (no delete confirmation) and is gone from
    # the header.
    expect(panel_tabs.get_delete_confirmation_dialog()).to_have_count(0)
    expect(left.get_panel_tab("files")).to_have_count(0)
