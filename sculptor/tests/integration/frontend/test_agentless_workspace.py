"""Integration tests for workspaces that have no agents.

A workspace can exist with zero agents (it is created through the backend API
before any agent is added). Visiting it must render the full section shell —
sidebar, workspace header, and the section grid with an empty center offering
the add-panel quick actions — never a blank page.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.panel_empty_state import PlaywrightEmptySectionState
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import create_zero_agent_workspace
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to land on a usable workspace shell when my workspace has no agents yet")
def test_agentless_workspace_renders_section_shell(sculptor_instance_: SculptorInstance) -> None:
    """A zero-agent workspace renders the shell (sidebar + sections), not a blank page.

    Steps:
    1. Create a workspace with NO agent via the backend API and navigate to it.
    2. Verify the sidebar and workspace header render.
    3. Verify the center section renders its empty state with quick actions.
    4. Verify the default arrangement was seeded around the empty center: the
       expanded left section shows its Files/Changes/Commits tabs.
    """
    page = sculptor_instance_.page

    create_zero_agent_workspace(page, description="Agentless Shell WS")

    # Step 2: The shell renders — sidebar and workspace header.
    task_page = PlaywrightTaskPage(page)
    expect(task_page.get_workspace_sidebar()).to_be_visible()
    expect(task_page.get_workspace_header()).to_be_visible()

    # Step 3: The center section is present with the empty-state launcher (there
    # is no agent to fill it), including the "New agent" quick action.
    center = PlaywrightWorkspaceSection(page, "center")
    expect(center.get_section()).to_be_visible()
    empty_state = PlaywrightEmptySectionState(page, "center")
    expect(empty_state.get_add_panel_button()).to_be_visible()
    expect(empty_state.get_quick_action("new-agent")).to_be_visible()

    # Step 4: The rest of the default arrangement was seeded — the expanded left
    # section shows its seeded explorer tabs.
    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("files")).to_be_visible()
    expect(left.get_panel_tab("changes")).to_be_visible()
    expect(left.get_panel_tab("commits")).to_be_visible()


@user_story("to create the first agent of a workspace from the empty center")
def test_agentless_workspace_empty_state_creates_first_agent(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The empty center's "New agent" quick action creates and shows the first agent.

    Steps:
    1. Create a zero-agent workspace and navigate to it.
    2. Click the center empty state's "New agent" quick action.
    3. Verify an agent tab appears in the center and its chat panel renders.
    """
    page = sculptor_instance_.page

    create_zero_agent_workspace(page, description="Agentless First Agent WS")

    task_page = PlaywrightTaskPage(page)
    empty_state = PlaywrightEmptySectionState(page, "center")
    quick_action = empty_state.get_quick_action("new-agent")
    expect(quick_action).to_be_visible()
    quick_action.click()

    # The agent lands as a center tab and its chat renders.
    tabs = PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()
    expect(tabs).to_have_count(1)
    expect(task_page.get_chat_panel()).to_be_visible()
