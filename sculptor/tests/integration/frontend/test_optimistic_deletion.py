"""Integration tests for optimistic deletion of agents and workspaces.

These tests verify:
- Agent tabs disappear immediately on deletion (before backend confirms)
- Workspace tabs disappear immediately on deletion (before backend confirms)
- When the backend delete fails, the deleted item reappears and an error toast is shown
- The error toast offers a "Retry" button to re-attempt the deletion
"""

import json
import re

from playwright.sync_api import Page
from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to have agent tabs disappear instantly when deleted")
def test_optimistic_agent_deletion_removes_tab_immediately(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Delete an agent from a multi-agent workspace and verify the tab disappears instantly.

    Creates a workspace with two agents, deletes one via the close button,
    and asserts the tab count drops to 1 without waiting for the server.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Optimistic WS")

    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    agent_tab_bar.delete_agent_via_close_button(agent_tab_index=1)

    # Dialog closes and tab disappears immediately (optimistic)
    expect(agent_tab_bar.get_delete_confirmation_dialog()).to_be_hidden()
    expect(agent_tabs).to_have_count(1)


@user_story("to have agent tabs disappear instantly when deleted")
def test_optimistic_agent_deletion_last_agent_creates_new_one(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Delete the last agent in a workspace and verify a new agent is created.

    The workspace should remain with a fresh agent tab replacing the deleted one.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Only agent", workspace_name="Last Agent WS")

    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    agent_tab_bar.delete_agent_via_close_button(agent_tab_index=0)

    expect(agent_tab_bar.get_delete_confirmation_dialog()).to_be_hidden()

    # A new agent is created automatically — still one tab, but a different agent.
    # On slower runners the count briefly drops to 0 before the new agent appears.
    expect(agent_tabs).to_have_count(1)

    # The workspace tab should still exist
    layout = PlaywrightProjectLayoutPage(page=page)
    expect(layout.get_workspace_tabs()).to_have_count(1)


@user_story("to have workspace tabs disappear instantly when deleted")
def test_optimistic_workspace_deletion_removes_tab_immediately(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Delete a workspace and verify the tab disappears instantly.

    Creates two workspaces, deletes one via the context menu, and asserts
    the workspace tab count drops without waiting for the server.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="WS1 agent", workspace_name="Workspace One")
    start_task_and_wait_for_ready(page, prompt="WS2 agent", workspace_name="Workspace Two")

    layout = PlaywrightProjectLayoutPage(page=page)
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    layout.delete_workspace_via_context_menu(workspace_tab_index=0)

    expect(layout.get_delete_confirmation_dialog()).to_be_hidden()
    # Optimistic delete removes the tab immediately, but on slower runners
    # the DOM update may lag behind the dialog dismissal.
    expect(workspace_tabs).to_have_count(1)


@user_story("to see an agent restored when deletion fails")
def test_agent_deletion_failure_rolls_back_and_shows_error_toast(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Simulate a server failure on agent deletion and verify rollback.

    Uses Playwright route interception to make the DELETE API call return 500.
    The agent tab should reappear and a prominent error toast should be shown.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Rollback WS")

    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Intercept the DELETE agent API call and return a 500 error
    agent_delete_pattern = re.compile(r"/api/v1/workspaces/.+/agents/.+")

    def fail_agent_delete(route: Route) -> None:
        if route.request.method == "DELETE":
            route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
        else:
            route.continue_()

    page.route(agent_delete_pattern, fail_agent_delete)

    try:
        agent_tab_bar.delete_agent_via_close_button(agent_tab_index=1)

        # Tab disappears optimistically
        expect(agent_tab_bar.get_delete_confirmation_dialog()).to_be_hidden()

        # After the API failure, the tab should reappear (rollback)
        expect(agent_tabs).to_have_count(2)

        # An error toast should be visible
        toast = PlaywrightToastElement(page)
        expect(toast).to_be_visible()
        expect(toast).to_contain_text("Failed to delete")
        expect(toast).to_contain_text("Retry")
    finally:
        page.unroute(agent_delete_pattern, fail_agent_delete)


@user_story("to retry a failed agent deletion")
def test_agent_deletion_failure_retry_succeeds(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After a failed agent deletion, clicking Retry should re-attempt the delete.

    First forces a 500 error, then removes the route intercept so the retry
    goes through to the real server and succeeds.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Retry WS")

    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tab_bar.get_add_agent_button().click()

    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # Intercept the DELETE agent API call and return a 500 error
    agent_delete_pattern = re.compile(r"/api/v1/workspaces/.+/agents/.+")

    def fail_agent_delete(route: Route) -> None:
        if route.request.method == "DELETE":
            route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
        else:
            route.continue_()

    page.route(agent_delete_pattern, fail_agent_delete)

    agent_tab_bar.delete_agent_via_close_button(agent_tab_index=1)

    # Wait for rollback: 2 tabs again
    expect(agent_tabs).to_have_count(2)

    # Error toast should be visible with Retry
    toast = PlaywrightToastElement(page)
    expect(toast).to_be_visible()
    expect(toast).to_contain_text("Retry")

    # Remove the intercept so the retry goes through to the real server
    page.unroute(agent_delete_pattern, fail_agent_delete)

    # Click the Retry button on the toast
    toast.get_action_button().click()

    # Now the deletion should succeed — tab count drops to 1
    expect(agent_tabs).to_have_count(1)


@user_story("to see a workspace restored when deletion fails")
def test_workspace_deletion_failure_rolls_back_and_shows_error_toast(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Simulate a server failure on workspace deletion and verify rollback.

    Uses Playwright route interception to make the DELETE API call return 500.
    The workspace tab should reappear and a prominent error toast should be shown.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="WS1 agent", workspace_name="Workspace One")
    start_task_and_wait_for_ready(page, prompt="WS2 agent", workspace_name="Workspace Two")

    layout = PlaywrightProjectLayoutPage(page=page)
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # Intercept the DELETE workspace API call and return a 500 error
    workspace_delete_pattern = re.compile(r"/api/v1/workspaces/[^/]+$")

    def fail_workspace_delete(route: Route) -> None:
        if route.request.method == "DELETE":
            route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
        else:
            route.continue_()

    page.route(workspace_delete_pattern, fail_workspace_delete)

    try:
        layout.delete_workspace_via_context_menu(workspace_tab_index=0)

        expect(layout.get_delete_confirmation_dialog()).to_be_hidden()

        # After the API failure, the workspace tab should reappear (rollback)
        expect(workspace_tabs).to_have_count(2)

        # An error toast should be visible
        toast = PlaywrightToastElement(page)
        expect(toast).to_be_visible()
        expect(toast).to_contain_text("Failed to delete")
        expect(toast).to_contain_text("Retry")
    finally:
        page.unroute(workspace_delete_pattern, fail_workspace_delete)


def _read_tabs_state(page: Page) -> dict:
    """Read the persisted sculptor-tabs JSON from localStorage."""
    raw = page.evaluate("() => window.localStorage.getItem('sculptor-tabs')")
    assert raw is not None, "sculptor-tabs is not in localStorage"
    return json.loads(raw)


@user_story("to land on a valid tab after deleting the workspace I was viewing")
def test_deleting_active_workspace_clamps_active_index(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting the currently-active workspace must keep activeIndex pointing at a valid surviving tab.

    Creates two workspaces (so the order is [A, B] with B active because it was
    the most recently created), deletes B (the active one), and asserts the
    persisted activeIndex points at the surviving tab (A) — not at the removed
    slot.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="WS A agent", workspace_name="Workspace A")
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    layout = PlaywrightProjectLayoutPage(page=page)
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # The most recently created workspace (B) is active.
    layout.delete_workspace_via_context_menu(workspace_tab_index=1)
    expect(layout.get_delete_confirmation_dialog()).to_be_hidden()
    expect(workspace_tabs).to_have_count(1)

    # After deletion, activeIndex should point at a valid entry whose tabId
    # matches whatever URL the user was navigated to.
    page.wait_for_function(
        """
        () => {
          const r = window.localStorage.getItem('sculptor-tabs');
          if (!r) return false;
          const t = JSON.parse(r);
          return t.order.length === 1 && t.activeIndex >= 0 && t.activeIndex < t.order.length;
        }
        """,
    )
    tabs = _read_tabs_state(page)
    assert len(tabs["order"]) == 1
    assert 0 <= tabs["activeIndex"] < len(tabs["order"])


@user_story("to keep my active tab unchanged when I delete a different workspace")
def test_deleting_non_active_workspace_preserves_active_index(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting a non-active workspace must keep activeIndex pointing at the same tab.

    Creates two workspaces (so the order is [A, B] with B active), deletes A
    (the non-active one), and asserts the persisted activeIndex points at B
    (which moved from index 1 to index 0).
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="WS A agent", workspace_name="Workspace A")
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    layout = PlaywrightProjectLayoutPage(page=page)
    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    # Capture B's tabId (the active workspace) before we delete A.
    active_tab_id_before = page.evaluate(
        """
        () => {
          const t = JSON.parse(window.localStorage.getItem('sculptor-tabs') || '{}');
          return t.order && t.order[t.activeIndex] ? t.order[t.activeIndex].tabId : null;
        }
        """
    )
    assert active_tab_id_before is not None

    # Delete A (workspace_tab_index=0).
    layout.delete_workspace_via_context_menu(workspace_tab_index=0)
    expect(layout.get_delete_confirmation_dialog()).to_be_hidden()
    expect(workspace_tabs).to_have_count(1)

    # After deletion, the active tab should still be B (now at index 0).
    page.wait_for_function(
        """
        () => {
          const r = window.localStorage.getItem('sculptor-tabs');
          if (!r) return false;
          const t = JSON.parse(r);
          return t.order.length === 1 && t.activeIndex === 0;
        }
        """,
    )
    tabs = _read_tabs_state(page)
    assert tabs["order"][tabs["activeIndex"]]["tabId"] == active_tab_id_before
