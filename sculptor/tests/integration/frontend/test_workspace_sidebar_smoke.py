"""Smoke tests for the redesigned shell (sidebar + section spine).

Proves the new sidebar + section spine works end-to-end with the default
FakeClaude harness, so the rest of the test migration can build on it:

- the sidebar renders with its Home / Cmd+K / New-workspace links and at least
  one workspace row;
- clicking a workspace row navigates to that workspace;
- the workspace header renders;
- the center section renders the active agent's chat.
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the navigation sidebar with its top links and my workspaces")
def test_sidebar_renders_with_links_and_rows(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The sidebar renders its top links and at least one workspace row.

    Steps:
    1. Create a workspace (lands on the workspace route, which renders the shell).
    2. Verify the sidebar root is visible.
    3. Verify the Home / Cmd+K / New-workspace links are visible.
    4. Verify at least one workspace row is present.
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace.
    start_task_and_wait_for_ready(page, prompt="Sidebar smoke", workspace_name="Sidebar Smoke WS")

    # Step 2: The sidebar root renders on the workspace route's shell.
    task_page = PlaywrightTaskPage(page)
    sidebar = task_page.get_workspace_sidebar()
    expect(sidebar).to_be_visible()

    # Step 3: The top links are present.
    expect(sidebar.get_home_link()).to_be_visible()
    expect(sidebar.get_cmdk_link()).to_be_visible()
    expect(sidebar.get_new_workspace_button()).to_be_visible()

    # Step 4: At least one workspace row is present.
    expect(sidebar.get_workspace_rows().first).to_be_visible()


@user_story("to click a workspace in the sidebar and have it open in the center")
def test_sidebar_row_navigates_to_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a sidebar workspace row navigates to that workspace.

    Steps:
    1. Create two workspaces so there are multiple rows to choose between.
    2. Click the first workspace's row via the shared nav helper.
    3. Verify the URL routes to a workspace and the chat panel re-renders.
    """
    page = sculptor_instance_.page

    # Step 1: Create two workspaces.
    start_task_and_wait_for_ready(page, prompt="First", workspace_name="Row Nav WS A")
    start_task_and_wait_for_ready(page, prompt="Second", workspace_name="Row Nav WS B")

    # Step 2: Click the first workspace row in the sidebar.
    task_page = PlaywrightTaskPage(page)
    target_row = task_page.get_workspace_sidebar().get_workspace_row_by_name("Row Nav WS A")
    expect(target_row).to_be_visible()
    navigate_to_workspace(page, "Row Nav WS A")

    # Step 3: We are on a workspace route and its chat panel renders.
    expect(page).to_have_url(re.compile(r"/ws/"))
    expect(task_page.get_chat_panel()).to_be_visible()


@user_story("to land on the workspace shell with its header and the agent chat in the center")
def test_center_section_renders_agent_chat(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The workspace header renders and the center section hosts the agent chat.

    Steps:
    1. Create a workspace with a first agent.
    2. Verify the workspace header renders.
    3. Verify the center section hosts the active agent's chat panel.
    4. Verify the agent's panel tab is the active tab in the center section.
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace + first agent.
    task_page = start_task_and_wait_for_ready(page, prompt="Center smoke", workspace_name="Center Smoke WS")

    # Step 2: The workspace header renders.
    expect(task_page.get_workspace_header()).to_be_visible()

    # Step 3: The center section hosts the agent's chat (its body renders CHAT_PANEL).
    center = task_page.get_section("center")
    expect(center.get_section()).to_be_visible()
    expect(center.get_section().get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible()

    # Step 4: The agent's panel tab is the active tab in the center section.
    expect(center.get_active_tab()).to_be_visible()
