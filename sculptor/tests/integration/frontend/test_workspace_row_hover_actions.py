"""Integration tests for the workspace row's hover-revealed actions.

The old workspace tab strip (and its hover peek popover) is gone; a workspace's
quick actions now live on its sidebar row, revealed on hover. This rebuilds the
hover affordance of ``test_workspace_peek`` against the row: the "..." actions
dropdown and the delete icon are hidden until the row is hovered, then appear and
are operable. (The scrolled-tab variant is dropped — there is no tab strip to
overflow.)
"""

from playwright.sync_api import expect

from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to reveal a workspace row's quick actions by hovering it")
def test_workspace_row_actions_appear_on_hover(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The "..." menu and delete icons are hidden until the row is hovered.

    Steps:
    1. Create a workspace
    2. Move the mouse away and verify the row action icons are hidden
    3. Hover the row and verify the "..." menu and delete icons appear
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="Hover task", workspace_name="Hover Actions WS")

    row = sidebar.get_workspace_rows().first
    expect(row).to_be_visible()

    # Step 2: With the mouse away from the row, the actions cluster is hidden.
    page.mouse.move(0, 0)
    expect(sidebar.get_row_menu_icon(row)).to_be_hidden()
    expect(sidebar.get_row_delete_icon(row)).to_be_hidden()

    # Step 3: Hovering the row reveals the "..." menu and delete icons.
    row.hover()
    expect(sidebar.get_row_menu_icon(row)).to_be_visible()
    expect(sidebar.get_row_delete_icon(row)).to_be_visible()


@user_story("to open a workspace's actions menu from its row dropdown")
def test_workspace_row_dropdown_opens_actions_menu(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking the hover-revealed "..." dropdown opens the workspace actions menu.

    Steps:
    1. Create a workspace
    2. Open the row's "..." dropdown menu
    3. Verify the Rename action is present in the menu
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="Menu task", workspace_name="Row Dropdown WS")

    row = sidebar.get_workspace_rows().first
    sidebar.open_row_dropdown_menu(row)

    # The dropdown surfaces the shared workspace actions (Rename / Close / Delete).
    expect(sidebar.get_context_menu_rename()).to_be_visible()
