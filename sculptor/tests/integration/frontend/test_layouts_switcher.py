"""Integration tests for the Layouts switcher (SCU-1725).

Cover the switcher end to end the way a user drives it: open it from the sidebar,
save the current arrangement as a named layout, and use "Apply & tidy" to close a
panel a layout doesn't include (while agents/terminals stay put).

FakeClaude's default response is enough here — these tests exercise the layout UI,
not agent behavior.
"""

from playwright.sync_api import expect

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
    # A fresh workspace always has the undeletable System Default.
    expect(switcher.get_system_default_row()).to_be_visible()
    expect(switcher.get_rows()).to_have_count(1)

    switcher.open_save_dialog().save("Deep work")

    # Reopening shows the new layout alongside System Default, and the just-saved one
    # is marked as the workspace's current layout.
    switcher = sidebar.open_layouts_switcher()
    expect(switcher.get_rows()).to_have_count(2)
    deep_work_row = switcher.get_row_by_name("Deep work")
    expect(deep_work_row).to_be_visible()
    expect(deep_work_row).to_contain_text("Current")


@user_story("to tidy a workspace to a layout, closing the panels it doesn't include")
def test_apply_and_tidy_closes_undeclared_static_panel(sculptor_instance_: SculptorInstance) -> None:
    """Apply & tidy to System Default closes an undeclared static panel (Notes) after
    confirmation, while the declared panels — and the agent — stay put."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Tidy Layout WS")

    # Add Notes to the left section — System Default declares Files/Changes/Commits
    # there, so Notes is exactly the residue "tidy" should close.
    open_panel(page, "notes", "left")
    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("notes")).to_be_visible()

    sidebar = get_workspace_sidebar(page)
    switcher = sidebar.open_layouts_switcher()
    switcher.apply_and_tidy_highlighted()

    # Something would close, so the confirmation appears; it names Notes.
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
