"""Regression test: Agent count in diagnostics overlay should match settings page.

Bug: The diagnostics overlay (VersionPopover) shows "Active Agents" from the
health check endpoint, which uses get_active_tasks(). This query only filtered
is_deleted but not is_deleting, so tasks in the process of being deleted were
still counted. Meanwhile, the settings page agent count comes from the frontend
task state (via WebSocket), which uses get_tasks_for_user() — a query that
filters both is_deleted and is_deleting. This caused the diagnostics count to
be higher than the settings page count whenever agents were being deleted.

Root cause: get_active_tasks() in sql_implementation.py was missing a
.where(is_deleting.is_(False)) filter that get_tasks_for_user() already had.
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _get_health_check_active_task_count(page: Page, base_url: str) -> int:
    """Call the health check API and return the activeTaskCount."""
    response = page.request.get(f"{base_url}/api/v1/health")
    assert response.ok, f"Health check failed: {response.status}"
    data = response.json()
    return int(data["activeTaskCount"])


def _get_settings_total_agent_count(page: Page) -> int:
    """Navigate to settings, read the agent count from each project row, and return the total."""
    settings_page = navigate_to_settings_page(page=page)
    # Wait for the settings page to be fully rendered before interacting
    expect(settings_page.get_settings_page_locator()).to_be_visible()
    repos_settings = settings_page.click_on_repositories()

    repo_rows = repos_settings.get_repo_rows()
    expect(repo_rows.first).to_be_visible()

    total = 0
    for row in repo_rows.all():
        # The row text contains e.g. "3 agents" or "1 agent"
        row_text = row.inner_text()
        match = re.search(r"(\d+)\s+agents?", row_text)
        if match:
            total += int(match.group(1))
    return total


@user_story("to see consistent agent counts between the settings page and diagnostics overlay")
def test_agent_count_matches_between_settings_and_diagnostics(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Agent count in diagnostics overlay should match the settings page total.

    Steps:
    1. Create a workspace with an agent that asks a user question (stays running)
    2. Delete the running agent via the close button
    3. Read the health check API's activeTaskCount
    4. Read the settings page's total agent count across all project rows
    5. Assert they match
    """
    page = sculptor_instance_.page
    base_url = sculptor_instance_.backend_api_url

    # Create a workspace with an agent that asks a user question.
    # This keeps the agent in RUNNING state, waiting for user input.
    task_page = start_task_and_wait_for_ready(
        page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Pick a language",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
        workspace_name="Agent Count Test WS",
    )

    # Wait for the Q&A panel to appear (agent is running and waiting for user input)
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible()

    # Delete the agent via the close button on the agent tab. The tab removal is
    # optimistic (it vanishes before the backend confirms), so the DELETE
    # response is the real sync point: waiting on it proves the backend has
    # committed is_deleting before we read any counts.
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    tabs = panel_tabs.get_panel_tabs()
    expect(tabs).to_have_count(1)
    with page.expect_response(lambda response: response.request.method == "DELETE" and "/agents/" in response.url):
        panel_tabs.delete_panel_via_close_button(f"agent:{task_page.get_task_id()}")

    # Confirm the delete dialog closed and the (optimistically removed) tab is
    # gone. Closing the last agent leaves the center section empty — no
    # replacement is auto-created — so the tab count settles at zero.
    expect(panel_tabs.get_delete_confirmation_dialog()).to_be_hidden()
    expect(tabs).to_have_count(0)

    # Now compare: the health check API count should match the settings page count.
    # With the bug, the health check would still count the is_deleting task,
    # while the settings page (fed by the frontend stream) would not.
    health_check_count = _get_health_check_active_task_count(page, base_url)
    settings_count = _get_settings_total_agent_count(page)

    assert health_check_count == settings_count, (
        f"Agent count mismatch: health check API reports {health_check_count} active agents, "
        + f"but settings page shows {settings_count}. "
        + "This indicates get_active_tasks() is not filtering is_deleting tasks."
    )
