"""Integration test for the Cmd+K "Reset to default layout" command.

The default test layout has only the center section expanded; the left, right, and
bottom sections are collapsed and render no header until expanded. Expanding a
section makes the layout non-default, and the reset command (after its confirmation)
must restore the default arrangement, re-collapsing it.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import wait_for_workspace_list_loaded
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to reset a customized workspace layout back to the default from Cmd+K")
def test_reset_layout_command_restores_default(sculptor_instance_: SculptorInstance) -> None:
    """The reset command restores the default arrangement after the layout is changed."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Reset Layout WS")
    wait_for_workspace_list_loaded(page)

    center = PlaywrightWorkspaceSection(page, "center")
    left = PlaywrightWorkspaceSection(page, "left")
    # Default layout: the left section is collapsed (renders no header).
    expect(left.get_header()).to_have_count(0)

    # Make the layout non-default by expanding the left section.
    left.expand_section()
    expect(left.get_header()).to_be_visible()

    # Reach the reset command through the Panels & Sections ("view.layout") sub-page,
    # where it lives alongside the section toggles.
    layout = PlaywrightProjectLayoutPage(page=page)
    palette = layout.open_command_palette()
    palette.type_query("Toggle sections")
    palette.select_by_command_id("view.toggle_layout")
    expect(palette.get_breadcrumb()).to_be_visible()
    # Clear the query left over from the entry-point search so every sub-page row shows.
    palette.clear_search()

    # The reset row carries its own dedicated data-testid (not the shared
    # COMMAND_PALETTE_ITEM one); confirm that override is present, then select it.
    reset_row = palette.get_item_by_command_id("view.reset_layout")
    expect(reset_row).to_be_visible()
    expect(reset_row).to_have_attribute("data-testid", ElementIDs.COMMAND_PALETTE_RESET_LAYOUT)
    palette.select_by_command_id("view.reset_layout")

    # Selecting the command opens a confirmation rather than resetting instantly.
    dialog = layout.get_confirmation_dialog()
    expect(dialog).to_be_visible()
    layout.confirm_confirmation_dialog()
    expect(dialog).not_to_be_visible()

    # The reset restored the default arrangement: the left section is collapsed again,
    # and the center (which can never collapse) still holds the agent.
    expect(left.get_header()).to_have_count(0)
    expect(center.get_header()).to_be_visible()
    expect(center.get_panel_tabs()).to_have_count(1)
