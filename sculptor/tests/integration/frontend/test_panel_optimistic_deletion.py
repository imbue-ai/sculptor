"""Integration tests for optimistic agent deletion via the panel tab.

Closing an agent panel tab deletes the underlying agent optimistically: the tab
disappears instantly, and a failed backend delete rolls back (the tab reappears) with
a prominent error toast that offers Retry. Closing the LAST agent leaves the center
section empty — no auto-created replacement.

These cases are the agent portion of the old `test_optimistic_deletion.py`,
re-anchored onto the panel-tab close flow; they replace its old "last agent →
auto-create a new one" assertion with the empty-center behaviour. The
workspace-deletion portion lives with the sidebar tests.
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_AGENT_DELETE_PATTERN = re.compile(r"/api/v1/workspaces/.+/agents/.+")


def _panel_id_of(tab: Locator) -> str:
    """Extract a panel tab's panel id from its ``PANEL_TAB-<panelId>`` testid."""
    testid = tab.get_attribute("data-testid")
    assert testid is not None and testid.startswith("PANEL_TAB-"), f"unexpected tab testid: {testid!r}"
    return testid[len("PANEL_TAB-") :]


def _fail_agent_delete(route: Route) -> None:
    """Fulfil DELETE agent requests with a 500; pass everything else through."""
    if route.request.method == "DELETE":
        route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
    else:
        route.continue_()


@user_story("to have an agent tab disappear instantly when I close it")
def test_optimistic_agent_deletion_removes_tab_immediately(sculptor_instance_: SculptorInstance) -> None:
    """Closing an agent panel tab removes it instantly (before the backend confirms)."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Optimistic Panel WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_id = _panel_id_of(tabs.nth(1))
    panel_tabs.delete_panel_via_close_button(panel_id)

    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(tabs).to_have_count(1)


@user_story("to not have a replacement agent auto-created when I close my last one")
def test_optimistic_deletion_last_agent_does_not_auto_create(sculptor_instance_: SculptorInstance) -> None:
    """Closing the last agent does NOT auto-create a replacement.

    Replaces the old "last agent → creates a new one" assertion: after the delete the
    center is left empty (no agent panel tab), rather than refilled.
    """
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Only agent", workspace_name="Empty Center Optimistic WS")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)

    panel_tabs.delete_panel_via_close_button(_panel_id_of(tabs.first))
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()

    # No replacement agent panel tab is auto-created.
    expect(panel_tabs.get_panel_tabs()).to_have_count(0)


@user_story("to see an agent restored with an error toast when deletion fails")
def test_agent_deletion_failure_rolls_back_and_shows_toast(sculptor_instance_: SculptorInstance) -> None:
    """A 500 on the agent delete rolls back the tab and shows an error toast with Retry."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Rollback Panel WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_id = _panel_id_of(tabs.nth(1))
    page.route(_AGENT_DELETE_PATTERN, _fail_agent_delete)
    try:
        panel_tabs.delete_panel_via_close_button(panel_id)
        expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()

        # The tab reappears (rollback) and a prominent error toast offers Retry.
        expect(tabs).to_have_count(2)
        toast = PlaywrightToastElement(page)
        expect(toast).to_be_visible()
        expect(toast).to_contain_text("Failed to delete")
        expect(toast).to_contain_text("Retry")
    finally:
        page.unroute(_AGENT_DELETE_PATTERN, _fail_agent_delete)


@user_story("to retry a failed agent deletion from the error toast")
def test_agent_deletion_failure_retry_succeeds(sculptor_instance_: SculptorInstance) -> None:
    """After a failed delete, clicking Retry (with the route cleared) removes the tab."""
    page = sculptor_instance_.page
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Agent 1", workspace_name="Retry Panel WS")
    create_agent_panel(page, section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(2)

    panel_id = _panel_id_of(tabs.nth(1))
    page.route(_AGENT_DELETE_PATTERN, _fail_agent_delete)
    panel_tabs.delete_panel_via_close_button(panel_id)

    # Rollback to 2 tabs with a Retry toast.
    expect(tabs).to_have_count(2)
    toast = PlaywrightToastElement(page)
    expect(toast).to_be_visible()
    expect(toast).to_contain_text("Retry")

    # Clear the intercept so the retry reaches the real server and succeeds.
    page.unroute(_AGENT_DELETE_PATTERN, _fail_agent_delete)
    toast.get_action_button().click()

    expect(tabs).to_have_count(1)
