"""Integration tests for the Layouts switcher (SCU-1725).

Cover the switcher end to end the way a user drives it: open it from the sidebar,
save the current arrangement as a named layout (optionally tidy-on-apply), apply a
layout so its tidy flag closes a panel it doesn't include (while agents/terminals
stay put), and drive a layout from its right-click context menu.

FakeClaude's default response is enough here — these tests exercise the layout UI,
not agent behavior.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.layouts import get_layout_tidy_dialog
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to save my current workspace arrangement as a named layout and switch back to it")
def test_switcher_opens_and_saves_a_layout(sculptor_instance_: SculptorInstance) -> None:
    """Opening the switcher shows System Default; saving the current arrangement adds a
    second layout, marked as the current one."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Save Layout WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    # A fresh workspace always has the undeletable System Default plus the built-in
    # task presets (Chat / Review / Terminal / Browser).
    expect(switcher.get_system_default_row()).to_be_visible()
    built_in_count = switcher.get_rows().count()
    assert built_in_count >= 1

    switcher.open_save_dialog().save("Deep work")

    # Reopening shows the new layout alongside the built-ins, and the just-saved one
    # is marked as the workspace's current layout.
    switcher = sidebar.open_layouts_switcher()
    expect(switcher.get_rows()).to_have_count(built_in_count + 1)
    deep_work_row = switcher.get_row_by_name("Deep work")
    expect(deep_work_row).to_be_visible()
    expect(deep_work_row).to_contain_text("Current")


@user_story("to tidy a workspace to a layout, closing the panels it doesn't include")
def test_tidy_on_apply_layout_closes_undeclared_static_panel(sculptor_instance_: SculptorInstance) -> None:
    """A layout saved with "tidy panels when applying" closes an undeclared static panel
    (Notes) on apply, after confirmation, while its declared panels — and the agent —
    stay put."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Tidy Layout WS")

    sidebar = get_workspace_sidebar(page)

    # Save the current arrangement (Files/Changes/Commits, no Notes) as a tidy-on-apply
    # layout, THEN open Notes — the undeclared residue this layout should close.
    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Base", tidy_on_apply=True)

    open_panel(page, "notes", "left")
    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    # Applying "Base" honors its tidy flag: something would close, so the confirmation
    # appears naming Notes.
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")

    tidy_dialog = get_layout_tidy_dialog(page)
    expect(tidy_dialog).to_be_visible()
    expect(tidy_dialog).to_contain_text("Notes")
    tidy_dialog.confirm()

    # Notes is gone; the layout's declared panels remain.
    expect(left.get_panel_tab("notes")).to_have_count(0)
    expect(left.get_panel_tab("files")).to_be_visible()

    # Agents are never closed by tidy — the center still holds the agent.
    center = PlaywrightWorkspaceSection(page, "center")
    expect(center.get_agent_tabs()).to_have_count(1)


@user_story("to edit a saved layout to stop it tidying panels when I apply it")
def test_edit_layout_turns_tidy_off(sculptor_instance_: SculptorInstance) -> None:
    """Editing a tidy-on-apply layout (via its right-click Edit) and flipping the tidy
    switch off means applying it no longer prompts to close undeclared panels."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Edit Tidy WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Base", tidy_on_apply=True)

    open_panel(page, "notes", "left")
    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    # Edit "Base" and turn tidy off, then re-apply: nothing closes and no prompt shows.
    switcher = sidebar.open_layouts_switcher()
    edit_dialog = switcher.open_edit_dialog("Base")
    edit_dialog.toggle_tidy_switch()
    edit_dialog.submit()

    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")

    expect(page.get_by_test_id(ElementIDs.LAYOUT_TIDY_DIALOG)).to_have_count(0)
    expect(left.get_panel_tab("notes")).to_be_visible()


@user_story("to stop layouts asking me to confirm tidying every time")
def test_tidy_confirmation_can_be_suppressed(sculptor_instance_: SculptorInstance) -> None:
    """Ticking "Don't show this again" in the Tidy confirmation makes later tidying
    apply silently, with no dialog."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Suppress Tidy WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Base", tidy_on_apply=True)

    left = PlaywrightWorkspaceSection(page, "left")
    open_panel(page, "notes", "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    # First apply prompts; confirm while suppressing future prompts for this layout.
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    tidy_dialog = get_layout_tidy_dialog(page)
    expect(tidy_dialog).to_be_visible()
    tidy_dialog.confirm(suppress_future=True)
    expect(left.get_panel_tab("notes")).to_have_count(0)

    # Reopen Notes and re-apply: it closes silently, with no confirmation this time.
    open_panel(page, "notes", "left")
    expect(left.get_panel_tab("notes")).to_be_visible()
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    expect(page.get_by_test_id(ElementIDs.LAYOUT_TIDY_DIALOG)).to_have_count(0)
    expect(left.get_panel_tab("notes")).to_have_count(0)


@user_story("to apply a layout from its right-click context menu")
def test_row_context_menu_applies_layout(sculptor_instance_: SculptorInstance) -> None:
    """Right-clicking a layout row opens the same actions as ⌘J; choosing Apply switches
    to that layout (marking it Current)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Context Menu WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Reviewing")
    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Debugging")

    # Right-click "Reviewing" and apply it from the context menu.
    switcher = sidebar.open_layouts_switcher()
    menu = switcher.open_row_context_menu("Reviewing")
    menu.get_by_test_id(ElementIDs.LAYOUTS_MORE_OPTIONS_APPLY).click()
    expect(page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_DIALOG)).to_be_hidden()

    # Reopening shows "Reviewing" as the current layout.
    switcher = sidebar.open_layouts_switcher()
    expect(switcher.get_row_by_name("Reviewing")).to_contain_text("Current")
