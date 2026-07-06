"""Integration tests for the seamless workspace-switch sequence.

Switching workspaces keeps the shell continuously present (no spinner, no blank
frame) and re-entering a workspace restores what the user was looking at (the
persisted active sub-section / expanded sections). The zero-reflow /
≤1-mount-per-panel ``[perf]`` guarantees are measured elsewhere, not asserted here.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to switch workspaces without a spinner or a blank frame")
def test_switch_keeps_the_shell_present(sculptor_instance_: SculptorInstance) -> None:
    """Switching to another workspace keeps the sidebar mounted and lands on its chat.

    The workspace sidebar is part of the persistent shell, so it stays visible across the
    switch (no full-page loader tears it down), and the destination's chat panel renders.
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Seamless A WS")
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Seamless B WS")

    sidebar = get_workspace_sidebar(page)
    expect(sidebar).to_be_visible()
    # Hold the exact sidebar DOM node. The sidebar is part of the persistent shell,
    # so a seamless switch keeps this same node mounted; a spinner/blank-frame
    # regression would unmount the shell and mount a fresh sidebar, which a plain
    # to_be_visible() re-query would still accept. Asserting the original node stays
    # connected is what actually catches a teardown/remount.
    sidebar_node = sidebar.element_handle()

    navigate_to_workspace(page, "Seamless A WS")

    # The shell never tears down (no spinner-gated blank): the sidebar stays visible
    # and the destination workspace's chat panel renders.
    expect(sidebar).to_be_visible()
    expect(PlaywrightTaskPage(page=page).get_chat_panel()).to_be_visible(timeout=60_000)
    # The very same sidebar node is still in the document — no full-page loader
    # replaced the shell mid-switch.
    assert sidebar_node.evaluate("el => el.isConnected"), "workspace sidebar was remounted during the switch"


@user_story("to return to a workspace and find the view I left")
def test_reentry_preserves_last_view(sculptor_instance_: SculptorInstance) -> None:
    """Re-entering a workspace restores its expanded sections, not the default.

    Expand the (default-collapsed) right section in workspace A, switch to B, then return
    to A — A's right section is still expanded (the last view is preserved, the default is
    not re-seeded over it).
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Reentry A WS")

    right_a = PlaywrightWorkspaceSection(page, "right")
    right_a.expand_section()
    expect(right_a.get_header()).to_be_visible()

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Reentry B WS")
    # B keeps its own default (right collapsed).
    expect(PlaywrightWorkspaceSection(page, "right").get_header()).to_have_count(0)

    navigate_to_workspace(page, "Reentry A WS")
    expect(PlaywrightTaskPage(page=page).get_chat_panel()).to_be_visible(timeout=60_000)
    # The view A was left in (right expanded) is restored.
    expect(PlaywrightWorkspaceSection(page, "right").get_header()).to_be_visible()
