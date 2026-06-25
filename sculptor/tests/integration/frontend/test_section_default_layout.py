"""Integration tests for the first-open default workspace layout (SEC-01..04).

On a workspace's FIRST visit the shell seeds the default arrangement (Tasks 6.1/6.2;
``goals.md`` → "Default layout"):

* center — the only expanded section, holding the active agent (SEC-01);
* left   — collapsed, with Files/Changes/Commits open and Files active (SEC-02);
* bottom — collapsed, with one terminal (SEC-03);
* right  — collapsed and empty (SEC-04).

These assert the seeded default by driving the section collapse/expand POMs the way a
user would (the seeded sections start collapsed; expanding one reveals its seeded
panels). This file was moved here from Phase 4 because it asserts the Task 6.1 seed,
which does not exist before Phase 6.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.panel_empty_state import PlaywrightEmptySectionState
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to land on my active agent in the center section when I open a new workspace")
def test_default_center_holds_the_active_agent(sculptor_instance_: SculptorInstance) -> None:
    """The center section is expanded and holds the active agent (SEC-01)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Default Center WS")

    center = PlaywrightWorkspaceSection(page, "center")
    # Center is always expanded (it has no collapse toggle, SEC-08) and shows the agent.
    expect(center.get_section_toggle()).to_have_count(0)
    # The active panel is an agent; the prefix matcher auto-retries through render settle.
    expect(center.get_active_tab()).to_have_attribute("data-panel-id", re.compile(r"^agent:"))


@user_story("to find Files/Changes/Commits ready in a collapsed left section")
def test_default_left_collapsed_with_files_changes_commits(sculptor_instance_: SculptorInstance) -> None:
    """Left starts collapsed; expanded it holds Files/Changes/Commits with Files active (SEC-02)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Default Left WS")

    left = PlaywrightWorkspaceSection(page, "left")
    # Collapsed by default: a collapsed section renders no header.
    expect(left.get_header()).to_have_count(0)

    left.expand_section()
    expect(left.get_panel_tab("files")).to_be_visible()
    expect(left.get_panel_tab("changes")).to_be_visible()
    expect(left.get_panel_tab("commits")).to_be_visible()
    # Files is the active panel, and the tab order is Files, Changes, Commits. Each
    # indexed assertion auto-retries until the tabs render in the expected order.
    expect(left.get_active_tab()).to_have_attribute("data-panel-id", "files")
    expect(left.get_panel_tabs()).to_have_count(3)
    expect(left.get_panel_tabs().nth(0)).to_have_attribute("data-panel-id", "files")
    expect(left.get_panel_tabs().nth(1)).to_have_attribute("data-panel-id", "changes")
    expect(left.get_panel_tabs().nth(2)).to_have_attribute("data-panel-id", "commits")


@user_story("to find one terminal ready in a collapsed bottom section")
def test_default_bottom_collapsed_with_one_terminal(sculptor_instance_: SculptorInstance) -> None:
    """Bottom starts collapsed; expanded it holds exactly one terminal (SEC-03)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Default Bottom WS")

    bottom = PlaywrightWorkspaceSection(page, "bottom")
    expect(bottom.get_header()).to_have_count(0)

    bottom.expand_section()
    expect(bottom.get_panel_tabs()).to_have_count(1)
    # The only panel is a terminal; the prefix matcher auto-retries through render settle.
    expect(bottom.get_active_tab()).to_have_attribute("data-panel-id", re.compile(r"^terminal:"))


@user_story("to start with a collapsed, empty right section")
def test_default_right_collapsed_and_empty(sculptor_instance_: SculptorInstance) -> None:
    """Right starts collapsed; expanded it is empty (no panels), showing the empty state (SEC-04)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Default Right WS")

    right = PlaywrightWorkspaceSection(page, "right")
    expect(right.get_header()).to_have_count(0)

    right.expand_section()
    # Nothing is seeded into the right section, so it shows the empty-state launcher.
    expect(right.get_panel_tabs()).to_have_count(0)
    expect(PlaywrightEmptySectionState(page, "right").get_add_panel_button()).to_be_visible()
