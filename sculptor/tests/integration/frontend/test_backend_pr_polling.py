"""Integration tests for backend-driven PR status polling.

Tests verify that the PrPollingService pushes status updates through the
WebSocket, that the home page shows PR badges, and that cached status
persists across navigation.

Each test installs its own fake ``gh`` CLI into
``sculptor_instance_.fake_bin_dir`` (which is always on the backend
subprocess's PATH).  ``SculptorInstance._pre_test`` empties the directory
between tests, so fake CLIs don't leak across tests.

After the rate-limit redesign the live poll round issues one token-wide
``search`` query (``is:pr state:open author:@me``) and fans the results out per
workspace; any branch the search doesn't match (terminal / no-PR) falls back to
the per-branch ``repository.pullRequests`` query. The fake ``gh`` below branches
on the query: an invocation carrying ``author:@me`` gets the **search** envelope;
the per-branch fallback (carrying ``branch=`` / ``owner=``) gets the
**repository** envelope.
"""

import json
import stat
import subprocess
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
_NAME_WITH_OWNER = "test-org/test-repo"

# Open PR surfaced through the SEARCH path. The search node's ``headRefName`` is
# the workspace's actual branch (read live via git, since the fake runs with
# cwd=working_dir), and ``nameWithOwner`` matches the fake origin, so the poller
# maps the node to this workspace. The per-branch fallback returns nothing — the
# open badge can only come from the search match, exercising the search path.
_FAKE_GH_SEARCH_OPEN = """\
#!/bin/bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [[ "$*" == *"author:@me"* ]]; then
    echo '{"data":{"search":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","repository":{"nameWithOwner":"test-org/test-repo"},"headRefName":"'"$BRANCH"'","mergeable":"MERGEABLE","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
elif [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
fi
"""

# Open PR sitting in the merge queue, surfaced through the SEARCH path (the
# primary path). Same shape as _FAKE_GH_SEARCH_OPEN but the search node reports
# isInMergeQueue:true, which drives the "Merge queued" status dot on the open-PR
# button. The per-branch fallback returns nothing.
_FAKE_GH_MERGE_QUEUED = """\
#!/bin/bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [[ "$*" == *"author:@me"* ]]; then
    echo '{"data":{"search":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","repository":{"nameWithOwner":"test-org/test-repo"},"headRefName":"'"$BRANCH"'","mergeable":"MERGEABLE","isInMergeQueue":true,"commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
elif [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
fi
"""

# Closed-not-merged PR. A closed PR is NOT in ``state:open`` search results, so
# this is driven entirely through the per-branch FALLBACK query returning a
# ``CLOSED`` node — exercising Change-2's terminal-state recovery.
_FAKE_GH_CLOSED = """\
#!/bin/bash
if [[ "$*" == *"author:@me"* ]]; then
    echo '{"data":{"search":{"nodes":[],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":1,"remaining":4999,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
elif [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":77,"title":"Closed PR","url":"https://github.com/test/repo/pull/77","state":"CLOSED","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
fi
"""

# Search envelope whose nodes come from a file the test rewrites, so the test
# controls exactly which branches have open PRs regardless of which workspace
# dir the token-wide search runs from. The per-branch fallback returns nothing.
# Mode/nodes paths are injected via ``.replace(...)`` (not ``.format``) so the
# JSON braces don't need escaping.
_FAKE_GH_SEARCH_NODES_FILE = """\
#!/bin/bash
if [[ "$*" == *"author:@me"* ]]; then
    NODES=$(cat "{nodes_file}")
    echo '{"data":{"search":{"nodes":'"$NODES"',"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
elif [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
fi
"""

# Drives one branch through open(clean) -> open(conflict) -> merged via a mode
# file. The two open states ride the SEARCH envelope (mergeable MERGEABLE then
# CONFLICTING, so has_conflicts flows to the CI babysitter); the merged state
# leaves ``state:open`` so it comes through the per-branch FALLBACK as MERGED.
_FAKE_GH_CONFLICT_MODE = """\
#!/bin/bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
MODE=$(cat "{mode_file}")
if [[ "$*" == *"author:@me"* ]]; then
    if [[ "$MODE" == "open_clean" ]]; then
        echo '{"data":{"search":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","repository":{"nameWithOwner":"test-org/test-repo"},"headRefName":"'"$BRANCH"'","mergeable":"MERGEABLE","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
    elif [[ "$MODE" == "open_conflict" ]]; then
        echo '{"data":{"search":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","repository":{"nameWithOwner":"test-org/test-repo"},"headRefName":"'"$BRANCH"'","mergeable":"CONFLICTING","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
    else
        echo '{"data":{"search":{"nodes":[],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":1,"remaining":4999,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
    fi
elif [[ "$*" == *"graphql"* ]]; then
    if [[ "$MODE" == "merged" ]]; then
        echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"MERGED","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
    else
        echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
    fi
fi
"""

# open_pr -> no_pr via a mode file: the search returns the branch's open node, or
# nothing. Used for the branch-switch test (switch branch + flip to no_pr).
_FAKE_GH_SWITCH_MODE = """\
#!/bin/bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
MODE=$(cat "{mode_file}")
if [[ "$*" == *"author:@me"* ]]; then
    if [[ "$MODE" == "open_pr" ]]; then
        echo '{"data":{"search":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","repository":{"nameWithOwner":"test-org/test-repo"},"headRefName":"'"$BRANCH"'","mergeable":"MERGEABLE","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
    else
        echo '{"data":{"search":{"nodes":[],"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":1,"remaining":4999,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
    fi
elif [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
fi
"""


def _open_search_nodes_json(branch: str, number: int = 42) -> str:
    """Build a one-node search ``nodes`` array (JSON) for a workspace branch."""
    node = {
        "number": number,
        "title": "Test PR",
        "url": f"https://github.com/test/repo/pull/{number}",
        "state": "OPEN",
        "baseRefName": "main",
        "repository": {"nameWithOwner": _NAME_WITH_OWNER},
        "headRefName": branch,
        "mergeable": "MERGEABLE",
        "commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]},
        "latestReviews": {"nodes": []},
        "reviewThreads": {"nodes": []},
    }
    return json.dumps([node])


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


def _get_worktree_working_dir(instance: SculptorInstance) -> Path:
    """Return the (single) workspace worktree's working directory.

    Worktree-mode workspaces share the user repo's ``.git``, so ``git worktree
    list`` on the user repo enumerates them; the one path that isn't the main
    checkout is the workspace's working dir.
    """
    user_repo_path = instance.project_path
    result = subprocess.run(
        ["git", "-C", str(user_repo_path), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    main_path = Path(user_repo_path).resolve()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            worktree_path = Path(line.removeprefix("worktree ").strip()).resolve()
            if worktree_path != main_path:
                return worktree_path
    raise AssertionError(f"No workspace worktree found under {user_repo_path}")


def _wait_for_open_pr_button(task_page: PlaywrightTaskPage) -> None:
    """Wait for the open PR button to appear (a search round resolved it)."""
    open_button = task_page.get_pr_button_open()
    expect(open_button).to_be_visible(timeout=60_000)
    expect(open_button).to_contain_text("PR #42")


@user_story("to see PR status badges on the home page workspace list")
def test_home_page_shows_pr_badge(sculptor_instance_: SculptorInstance) -> None:
    """When the batched search finds an open PR, the home page workspace row shows a PR badge."""
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_SEARCH_OPEN)
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


@user_story("to see when a GitHub PR is queued in the merge queue")
def test_merge_queued_pr_shows_dot(sculptor_instance_: SculptorInstance) -> None:
    """When the backend reports an open PR is in the merge queue, the open-PR
    button shows the "Merge queued" status dot."""
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_MERGE_QUEUED)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _wait_for_open_pr_button(task_page)

    merge_queued_dot = sculptor_instance_.page.get_by_test_id(ElementIDs.PR_BUTTON_MERGE_QUEUED)
    expect(merge_queued_dot).to_be_visible()


@user_story("to see cached PR status immediately when navigating between pages")
def test_cached_pr_status_no_loading_on_navigation(sculptor_instance_: SculptorInstance) -> None:
    """After the first poll, navigating away and back shows cached status without a loading spinner."""
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_SEARCH_OPEN)
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

    Workspace 1 has an open PR (its branch is in the search nodes); workspace 2
    does not (its branch is absent from the search, so it falls back to the
    per-branch query, which returns nothing → "Create PR"). This exercises the
    search fan-out *and* Change-2's fallback end-to-end.
    """
    nodes_file = tmp_path / "search_nodes"
    nodes_file.write_text("[]")
    _install_fake_gh(
        sculptor_instance_.fake_bin_dir, _FAKE_GH_SEARCH_NODES_FILE.replace("{nodes_file}", str(nodes_file))
    )
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    # Workspace 1: create it, then publish an open PR node for its branch.
    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    branch_1 = task_page.get_branch_name()
    nodes_file.write_text(_open_search_nodes_json(branch_1))
    _wait_for_open_pr_button(task_page)

    # Workspace 2: its branch is absent from the search nodes → "Create PR".
    task_page_2 = start_task_and_wait_for_ready(sculptor_instance_.page, "say goodbye")
    create_button = task_page_2.get_pr_button_create()
    expect(create_button).to_be_visible(timeout=60_000)

    # Navigate to home page — workspace 1 should still show the PR badge.
    navigate_to_home_page(sculptor_instance_.page)
    home_page = PlaywrightHomePage(sculptor_instance_.page)
    workspace_rows = home_page.get_workspace_rows()
    expect(workspace_rows).to_have_count(2)

    pr_buttons = home_page.get_pr_buttons_open()
    expect(pr_buttons).to_have_count(1)
    expect(pr_buttons.first).to_contain_text("PR #42")


@user_story("to see that a GitHub PR was closed without being merged, not get prompted to create a new one")
def test_closed_not_merged_pr_shows_closed_state(sculptor_instance_: SculptorInstance) -> None:
    """When the only PR on this branch was closed without being merged, the PR
    button reflects the closed state instead of falling back to "Create PR".

    A closed PR is absent from the ``state:open`` search, so it is recovered by
    the per-branch fallback query returning a ``state: CLOSED`` node.
    """
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_CLOSED)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")

    merged_or_closed_button = sculptor_instance_.page.get_by_test_id(ElementIDs.PR_BUTTON_MERGED)
    expect(merged_or_closed_button).to_be_visible(timeout=60_000)
    expect(merged_or_closed_button).to_contain_text("PR #77")
    expect(merged_or_closed_button).to_contain_text("closed")
    expect(merged_or_closed_button).to_have_attribute("data-pr-state", "closed")


@user_story("to see a PR's status update as it goes from open through a merge conflict to merged")
def test_open_to_conflict_to_merged_transition(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """An open PR that develops a merge conflict and is then merged surfaces the
    open → merged transition (passing through the conflict state).

    The conflict (``mergeable: CONFLICTING``) rides the open search node and
    drives ``has_conflicts`` for the CI babysitter; it has no dedicated PR-button
    affordance, so this asserts the open badge persists through the conflict
    state and the merged badge appears after — the behavioral transition. The
    ``has_conflicts`` flow itself is covered by the poller unit tests.
    """
    mode_file = tmp_path / "gh_mode"
    mode_file.write_text("open_clean")
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_CONFLICT_MODE.replace("{mode_file}", str(mode_file)))
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _wait_for_open_pr_button(task_page)

    # The PR develops a merge conflict — still open, badge persists.
    mode_file.write_text("open_conflict")
    open_button = task_page.get_pr_button_open()
    expect(open_button).to_be_visible()
    expect(open_button).to_contain_text("PR #42")

    # The PR is merged — it leaves state:open, so the fallback reports MERGED.
    mode_file.write_text("merged")
    merged_button = sculptor_instance_.page.get_by_test_id(ElementIDs.PR_BUTTON_MERGED)
    expect(merged_button).to_be_visible(timeout=60_000)
    expect(merged_button).to_contain_text("PR #42")
    expect(merged_button).to_contain_text("merged")
    expect(merged_button).to_have_attribute("data-pr-state", "merged")


@user_story("to see PR status re-resolve immediately when I switch the workspace's branch")
def test_branch_switch_triggers_immediate_repoll(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Switching the workspace's current branch clears the cached PR status and
    immediately re-resolves it (the retained on_branch_changed re-poll).
    """
    mode_file = tmp_path / "gh_mode"
    mode_file.write_text("open_pr")
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_SWITCH_MODE.replace("{mode_file}", str(mode_file)))
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    task_page = start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _wait_for_open_pr_button(task_page)

    # Switch to a fresh branch with no PR. The branch poller detects the change,
    # fires on_branch_changed (clears the cached status), and re-polls — the
    # fallback now finds no PR, so the badge re-resolves to "Create PR".
    mode_file.write_text("no_pr")
    workspace_dir = _get_worktree_working_dir(sculptor_instance_)
    subprocess.run(
        ["git", "checkout", "-b", "pr-switch-target"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    create_button = task_page.get_pr_button_create()
    expect(create_button).to_be_visible(timeout=30_000)
    expect(task_page.get_pr_button_open()).to_be_hidden()
