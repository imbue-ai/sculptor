"""Integration tests for optimistic close of workspace tabs.

Verifies:
- When the backend close API fails, the workspace tab reappears and an error
  toast with a Retry button is shown.

Complements the unit-level tests in
`sculptor/frontend/src/common/state/atoms/workspaces.test.ts`, which cover the
state-level behavior (pending-close suppression, error toast atom set on
rejection). This test covers the UI wiring: the toast actually renders.
"""

import json
import re

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see an error toast when closing a workspace tab fails")
def test_workspace_close_failure_shows_error_toast(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Simulate a server failure on workspace close and verify the toast renders.

    Uses Playwright route interception to make the PATCH /workspaces/{id}
    call with isOpen=false return 500. The tab should un-hide (pending-close
    cleared) and a prominent error toast with a Retry action should appear.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page)
    toast_element = PlaywrightToastElement(page)

    start_task_and_wait_for_ready(page, prompt="WS1 agent", workspace_name="Workspace One")
    start_task_and_wait_for_ready(page, prompt="WS2 agent", workspace_name="Workspace Two")

    workspace_tabs = layout.get_workspace_tabs()
    expect(workspace_tabs).to_have_count(2)

    pill = layout.get_closed_workspaces_pill()
    # Precondition: with both workspaces open, the closed-workspaces pill is hidden.
    expect(pill).not_to_be_visible()

    # Intercept only the "close" PATCH (isOpen=false), so unrelated workspace
    # updates (description, target branch, isOpen=true) pass through untouched.
    workspace_update_pattern = re.compile(r"/api/v1/workspaces/[^/]+$")

    def fail_workspace_close(route: Route) -> None:
        request = route.request
        if request.method != "PATCH":
            route.continue_()
            return
        try:
            body = json.loads(request.post_data or "{}")
        except json.JSONDecodeError:
            route.continue_()
            return
        if body.get("isOpen") is False:
            route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
        else:
            route.continue_()

    page.route(workspace_update_pattern, fail_workspace_close)

    try:
        layout.close_workspace_tab_via_context_menu(workspace_tab_index=0)

        # After the API failure, the workspace tab reappears (pending-close cleared)
        expect(workspace_tabs).to_have_count(2)

        toast = toast_element.get_toasts()
        expect(toast).to_be_visible()
        expect(toast).to_contain_text("Failed to close workspace")
        expect(toast).to_contain_text("Retry")

        # The actual user-visible behavior: the close didn't take effect, so
        # the workspace must NOT show up as closed in the pill. Without the
        # pendingClose rollback in `.catch`, a stale optimistic pill would
        # linger and tell the user "1 workspace is closed" when none is.
        expect(pill).not_to_be_visible()
    finally:
        page.unroute(workspace_update_pattern, fail_workspace_close)
