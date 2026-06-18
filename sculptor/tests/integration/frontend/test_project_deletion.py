"""Integration tests for project deletion cascading to its workspaces."""

import re

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _extract_workspace_id(url: str) -> str:
    """Extract the workspace ID from a Sculptor URL (format: /ws/{workspaceID}/agent/...)."""
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    if not match:
        raise ValueError(f"Could not extract workspace ID from URL: {url}")
    return match.group(1)


@user_story("to have workspaces cleaned up when I delete a project")
def test_deleting_project_also_deletes_its_workspaces(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Deleting a project should also soft-delete all workspaces belonging to it."""
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page

        start_task_and_wait_for_ready(
            sculptor_page=page,
            prompt="Setup task",
            workspace_name="Workspace To Delete",
        )

        workspace_id = _extract_workspace_id(page.url)
        base_url = page.url.split("#")[0].rstrip("/")

        get_response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert get_response.ok, f"Expected workspace {workspace_id} to exist, got status {get_response.status}"

        settings_page = navigate_to_settings_page(page=page)
        repos = settings_page.click_on_repositories()

        # Delete the first repo row (the original project). remove_first_repo
        # clicks remove, confirms, and waits for the row to hide — the cleanest
        # before/after signal that the request was submitted.
        repos.remove_first_repo()
        # Then wait for the repo row count to drop to zero.
        expect(repos.get_repo_rows()).to_have_count(0)

        get_response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert get_response.status == 404, (
            f"Expected workspace {workspace_id} to be deleted (404) after project deletion, but got status {get_response.status}"
        )
