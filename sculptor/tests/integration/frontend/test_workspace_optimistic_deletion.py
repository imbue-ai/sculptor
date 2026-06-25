"""Integration tests for optimistic workspace deletion from the sidebar (SIDE-16).

Deleting a workspace is destructive, so it is confirmed first via the shared
delete-confirmation dialog. Once confirmed, the removal is optimistic: the row
disappears before the backend confirms, and a failed delete rolls the row back
with a prominent error toast offering Retry.

This is the workspace half of the old `test_optimistic_deletion` (its agent half
moved to `test_panel_optimistic_deletion`) plus the rollback-toast behaviour from
`test_optimistic_close`, re-anchored onto the sidebar row.
"""

import json
import re

from playwright.sync_api import Page
from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WORKSPACE_DELETE_PATTERN = re.compile(r"/api/v1/workspaces/[^/]+$")


def _fail_workspace_delete(route: Route) -> None:
    """Fulfil DELETE workspace requests with a 500; pass everything else through."""
    if route.request.method == "DELETE":
        route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
    else:
        route.continue_()


@user_story("to confirm before deleting a workspace, and cancel to abort")
def test_workspace_delete_requires_confirmation(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The trash icon opens a confirmation dialog; cancelling leaves the workspace.

    Steps:
    1. Create a workspace
    2. Hover the row and click its trash icon
    3. Verify the delete-confirmation dialog appears
    4. Cancel and verify the row is still present
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="Keep me", workspace_name="Confirm WS")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(1)

    row = sidebar.get_workspace_rows().first
    row.hover()
    delete_icon = sidebar.get_row_delete_icon(row)
    expect(delete_icon).to_be_visible()
    delete_icon.click()

    # A confirmation dialog gates the destructive delete.
    dialog = sidebar.get_delete_confirmation_dialog()
    expect(dialog).to_be_visible()

    # Cancelling aborts: the workspace row is still present.
    sidebar.cancel_delete()
    expect(dialog).to_be_hidden()
    expect(rows).to_have_count(1)


@user_story("to have a workspace row disappear instantly when I confirm deleting it")
def test_optimistic_workspace_deletion_removes_row_immediately(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After confirming, deleting a workspace removes its row instantly (before the server confirms).

    Deletes a non-active workspace so no navigation is involved.
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="WS1 agent", workspace_name="Workspace One")
    start_task_and_wait_for_ready(page, prompt="WS2 agent", workspace_name="Workspace Two")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(2)

    # "Workspace Two" is active (most recently created); delete the non-active one.
    # The helper opens the confirmation dialog and confirms.
    sidebar.delete_workspace_via_row_icon(sidebar.get_workspace_row_by_name("Workspace One"))

    expect(sidebar.get_delete_confirmation_dialog()).to_be_hidden()
    expect(rows).to_have_count(1)


@user_story("to see a workspace restored with an error toast when deletion fails")
def test_workspace_deletion_failure_rolls_back_and_shows_toast(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A 500 on the workspace delete rolls the row back and shows an error toast with Retry."""
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="WS1 agent", workspace_name="Workspace One")
    start_task_and_wait_for_ready(page, prompt="WS2 agent", workspace_name="Workspace Two")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(2)

    page.route(_WORKSPACE_DELETE_PATTERN, _fail_workspace_delete)
    try:
        sidebar.delete_workspace_via_row_icon(sidebar.get_workspace_row_by_name("Workspace One"))

        # After the API failure, the row reappears (rollback) with a Retry toast.
        expect(rows).to_have_count(2)
        toast = PlaywrightToastElement(page)
        expect(toast).to_be_visible()
        expect(toast).to_contain_text("Failed to delete")
        expect(toast).to_contain_text("Retry")
    finally:
        page.unroute(_WORKSPACE_DELETE_PATTERN, _fail_workspace_delete)


@user_story("to retry a failed workspace deletion from the error toast")
def test_workspace_deletion_failure_retry_succeeds(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After a failed delete, clicking Retry (with the route cleared) removes the row."""
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="WS1 agent", workspace_name="Workspace One")
    start_task_and_wait_for_ready(page, prompt="WS2 agent", workspace_name="Workspace Two")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(2)

    page.route(_WORKSPACE_DELETE_PATTERN, _fail_workspace_delete)
    sidebar.delete_workspace_via_row_icon(sidebar.get_workspace_row_by_name("Workspace One"))

    # Rollback to 2 rows with a Retry toast.
    expect(rows).to_have_count(2)
    toast = PlaywrightToastElement(page)
    expect(toast).to_be_visible()
    expect(toast).to_contain_text("Retry")

    # Clear the intercept so the retry reaches the real server and succeeds.
    page.unroute(_WORKSPACE_DELETE_PATTERN, _fail_workspace_delete)
    toast.get_action_button().click()

    expect(rows).to_have_count(1)


def _read_tabs_state(page: Page) -> dict:
    """Read the persisted sculptor-tabs JSON from localStorage."""
    raw = page.evaluate("() => window.localStorage.getItem('sculptor-tabs')")
    assert raw is not None, "sculptor-tabs is not in localStorage"
    return json.loads(raw)


@user_story("to land on a valid workspace after deleting the one I was viewing")
def test_deleting_active_workspace_clamps_active_index(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting the active workspace keeps activeIndex pointing at a surviving tab.

    Creates two workspaces (B active because most recently created), deletes B
    (the active one), and asserts the persisted activeIndex points at a valid
    surviving entry.
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="WS A agent", workspace_name="Workspace A")
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(2)

    # The most recently created workspace (B) is active.
    sidebar.delete_workspace_via_row_icon(sidebar.get_workspace_row_by_name("Workspace B"))
    expect(rows).to_have_count(1)

    # After deletion, activeIndex should point at a valid surviving entry.
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


@user_story("to keep my active workspace unchanged when I delete a different one")
def test_deleting_non_active_workspace_preserves_active_index(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting a non-active workspace keeps activeIndex pointing at the same tab.

    Creates two workspaces (B active), deletes A (the non-active one), and asserts
    the persisted active tab is still B.
    """
    page = sculptor_instance_.page
    sidebar = get_workspace_sidebar(page)

    start_task_and_wait_for_ready(page, prompt="WS A agent", workspace_name="Workspace A")
    start_task_and_wait_for_ready(page, prompt="WS B agent", workspace_name="Workspace B")

    rows = sidebar.get_workspace_rows()
    expect(rows).to_have_count(2)

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

    # Delete A (the non-active workspace).
    sidebar.delete_workspace_via_row_icon(sidebar.get_workspace_row_by_name("Workspace A"))
    expect(rows).to_have_count(1)

    # After deletion, the active tab should still be B.
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
