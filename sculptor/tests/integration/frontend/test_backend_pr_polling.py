"""Integration tests for backend-driven PR status polling.

Tests verify that the PrPollingService pushes status updates through the
WebSocket, that the home page shows PR badges, and that cached status
persists across navigation.

Each test installs its own fake ``gh`` CLI into
``sculptor_instance_.fake_bin_dir`` (which is always on the backend
subprocess's PATH).  ``SculptorInstance._pre_test`` empties the directory
between tests, so fake CLIs don't leak across tests.
"""

import stat
import textwrap
from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_FAKE_GITHUB_REMOTE = "https://github.com/test-org/test-repo.git"

# Fake gh CLI that always returns an open PR.
# The backend issues a single `gh api graphql` query that returns every PR on
# the source branch (across all states) with its check/review/comment detail
# bundled in, and dispatches on each node's "state" field. So the fake emits
# the GraphQL response envelope with one node tagged "state": "OPEN" (no checks,
# reviews, or threads). ``statusCheckRollup`` is null when no checks have run.
_FAKE_GH_OPEN_PR_SCRIPT = """\
#!/bin/bash
if [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
fi
"""

# Fake gh CLI that returns a closed-not-merged PR. The backend dispatches on
# each node's "state" field, so the node is tagged "state": "CLOSED".
_FAKE_GH_CLOSED_PR_SCRIPT = """\
#!/bin/bash
if [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":77,"title":"Closed PR","url":"https://github.com/test/repo/pull/77","state":"CLOSED","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
fi
"""

# Fake gh that switches behavior via mode file (no_pr → open_pr). Each mode
# emits the GraphQL response envelope; no_pr returns an empty node list.
# The mode-file path is injected via ``.replace("{mode_file}", ...)`` (not
# ``.format``) so the JSON braces below don't need escaping.
_FAKE_GH_MODE_SCRIPT = """\
#!/bin/bash
MODE=$(cat "{mode_file}")
case "$MODE" in
    no_pr)
        echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
        ;;
    open_pr)
        echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
        ;;
esac
"""


def _install_fake_gh(fake_bin_dir: Path, script: str) -> None:
    """Write an executable fake ``gh`` script into the instance's fake_bin_dir."""
    script_path = fake_bin_dir / "gh"
    script_path.write_text(textwrap.dedent(script))
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)


def _set_remote(instance: SculptorInstance, url: str) -> None:
    """Replace the repo's origin with the given URL and reload the SPA."""
    repo = instance.repo
    try:
        repo.repo.run_git(("remote", "remove", "origin"))
    except Exception:
        pass
    repo.repo.run_git(("remote", "add", "origin", url))
    full_spa_reload(instance.page)


def _wait_for_open_pr_button(task_page: PlaywrightTaskPage) -> None:
    """Wait for the open PR button to appear (backend poll completed)."""
    open_button = task_page.get_pr_button_open()
    expect(open_button).to_be_visible(timeout=60_000)
    expect(open_button).to_contain_text("PR #42")


@user_story("to see PR status badges on the home page workspace list")
def test_home_page_shows_pr_badge(sculptor_instance_: SculptorInstance) -> None:
    """When the backend polls an open PR, the home page workspace row shows a PR badge."""
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_OPEN_PR_SCRIPT)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _wait_for_open_pr_button(task_page)

    navigate_to_home_page(sculptor_instance_.page)
    home_page = PlaywrightHomePage(sculptor_instance_.page)
    workspace_row = home_page.get_workspace_rows().first
    expect(workspace_row).to_be_visible()
    pr_button = workspace_row.get_by_test_id(ElementIDs.PR_BUTTON_OPEN)
    expect(pr_button).to_be_visible()
    expect(pr_button).to_contain_text("PR #42")


@user_story("to see cached PR status immediately when navigating between pages")
def test_cached_pr_status_no_loading_on_navigation(sculptor_instance_: SculptorInstance) -> None:
    """After the first poll, navigating away and back shows cached status without a loading spinner."""
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_OPEN_PR_SCRIPT)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _wait_for_open_pr_button(task_page)

    navigate_to_home_page(sculptor_instance_.page)
    home_page = PlaywrightHomePage(sculptor_instance_.page)
    workspace_row = home_page.get_workspace_rows().first
    expect(workspace_row).to_be_visible()

    workspace_row.click()

    # The open PR button should be visible immediately from the cache —
    # use a short timeout to ensure we're seeing the cached value, not
    # waiting for a fresh poll.
    open_button = task_page.get_pr_button_open()
    expect(open_button).to_be_visible(timeout=5000)
    expect(open_button).to_contain_text("PR #42")


@user_story("to see independent PR status for each workspace")
def test_multiple_workspaces_independent_pr_status(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Each workspace gets its own PR status from the PrPollingService.

    Create two workspaces: one with an open PR, one without. Verify they
    show the correct independent states on the home page.
    """
    mode_file = tmp_path / "gh_mode"
    mode_file.write_text("open_pr")
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_MODE_SCRIPT.replace("{mode_file}", str(mode_file)))
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    # Workspace 1: open PR
    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _wait_for_open_pr_button(task_page)

    # Switch to no_pr and create workspace 2
    mode_file.write_text("no_pr")
    task_page_2 = start_task_and_wait_for_ready(sculptor_instance_.page, "say goodbye")

    # Workspace 2 should show "Create PR" (no PR exists)
    create_button = task_page_2.get_pr_button_create()
    expect(create_button).to_be_visible()

    # Navigate to home page — workspace 1 should still show the PR badge
    navigate_to_home_page(sculptor_instance_.page)
    home_page = PlaywrightHomePage(sculptor_instance_.page)
    workspace_rows = home_page.get_workspace_rows()
    expect(workspace_rows).to_have_count(2)

    # At least one workspace row should have the open PR button
    pr_buttons = home_page.get_pr_buttons_open()
    expect(pr_buttons).to_have_count(1)
    expect(pr_buttons.first).to_contain_text("PR #42")


@user_story("to see that a GitHub PR was closed without being merged, not get prompted to create a new one")
def test_closed_not_merged_pr_shows_closed_state(sculptor_instance_: SculptorInstance) -> None:
    """When the only PR on this branch was closed without being merged, the PR
    button reflects the closed state instead of falling back to "Create PR".

    The fake ``gh`` CLI returns a single PR node tagged ``state: CLOSED``, so a
    backend that ignores closed PRs (the bug) would render "Create PR" and the
    assertion below would fail.
    """
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_CLOSED_PR_SCRIPT)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")

    merged_or_closed_button = sculptor_instance_.page.get_by_test_id(ElementIDs.PR_BUTTON_MERGED)
    expect(merged_or_closed_button).to_be_visible(timeout=60_000)
    expect(merged_or_closed_button).to_contain_text("PR #77")
    expect(merged_or_closed_button).to_contain_text("closed")
    expect(merged_or_closed_button).to_have_attribute("data-pr-state", "closed")
