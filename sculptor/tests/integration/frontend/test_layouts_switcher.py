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
from sculptor.testing.elements.layouts import get_save_layout_dialog
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
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


@user_story("to back out of tidying and keep the panels a layout would have closed")
def test_tidy_cancel_keeps_panel_but_layout_still_applies(sculptor_instance_: SculptorInstance) -> None:
    """Cancelling the Tidy confirmation leaves the undeclared Notes panel open — but the
    apply is additive and already ran before the prompt, so the layout is still Current."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Tidy Cancel WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Base", tidy_on_apply=True)

    open_panel(page, "notes", "left")
    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    tidy_dialog = get_layout_tidy_dialog(page)
    expect(tidy_dialog).to_be_visible()
    tidy_dialog.cancel()

    # Notes survives the cancelled tidy, yet "Base" is still the applied layout.
    expect(left.get_panel_tab("notes")).to_be_visible()
    switcher = sidebar.open_layouts_switcher()
    expect(switcher.get_row_by_name("Base")).to_contain_text("Current")


@user_story("to turn tidy confirmations back on from Settings after silencing them")
def test_settings_switch_reenables_tidy_confirmation(sculptor_instance_: SculptorInstance) -> None:
    """Suppressing the Tidy confirmation via "Don't show this again" tidies silently;
    flipping the Settings ▸ General switch back on makes a later tidy prompt again."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Reenable Tidy WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Base", tidy_on_apply=True)

    left = PlaywrightWorkspaceSection(page, "left")
    open_panel(page, "notes", "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    # First apply: confirm while suppressing future prompts, then prove silent tidying.
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    tidy_dialog = get_layout_tidy_dialog(page)
    expect(tidy_dialog).to_be_visible()
    tidy_dialog.confirm(suppress_future=True)
    expect(left.get_panel_tab("notes")).to_have_count(0)

    open_panel(page, "notes", "left")
    expect(left.get_panel_tab("notes")).to_be_visible()
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    expect(page.get_by_test_id(ElementIDs.LAYOUT_TIDY_DIALOG)).to_have_count(0)
    expect(left.get_panel_tab("notes")).to_have_count(0)

    # Re-enable confirmations from Settings (the switch is inverted: checked = confirm).
    settings_page = navigate_to_settings_page(page=page)
    general = settings_page.click_on_general()
    switch = general.get_tidy_confirmation_switch()
    expect(switch).not_to_be_checked()
    switch.click()
    expect(switch).to_be_checked()

    # Back in the workspace, re-applying to an untidy arrangement prompts again.
    navigate_to_workspace(page, "Reenable Tidy WS")
    open_panel(page, "notes", "left")
    expect(left.get_panel_tab("notes")).to_be_visible()
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    expect(get_layout_tidy_dialog(page)).to_be_visible()


@user_story("to jump from the tidy prompt straight into editing the layout")
def test_tidy_edit_link_opens_save_dialog_in_edit_mode(sculptor_instance_: SculptorInstance) -> None:
    """The tidy confirmation's "Edit layout" link (shown for the user's own layouts)
    dismisses the prompt and opens the save form in edit mode with the tidy switch on."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Tidy Edit Link WS")
    sidebar = get_workspace_sidebar(page)

    switcher = sidebar.open_layouts_switcher()
    switcher.open_save_dialog().save("Base", tidy_on_apply=True)

    open_panel(page, "notes", "left")
    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    switcher = sidebar.open_layouts_switcher()
    switcher.apply_by_name("Base")
    tidy_dialog = get_layout_tidy_dialog(page)
    expect(tidy_dialog).to_be_visible()
    tidy_dialog.edit_layout()

    save_dialog = get_save_layout_dialog(page)
    expect(save_dialog).to_be_visible()
    # Edit mode's visible marker is the submit label ("Save changes" vs create's
    # "Save layout") — the dialog's title itself is visually hidden.
    expect(save_dialog.get_submit_button()).to_have_text("Save changes")
    expect(save_dialog.get_tidy_switch()).to_be_checked()
