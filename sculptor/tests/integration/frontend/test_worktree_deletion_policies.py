"""Integration tests for the worktree branch-deletion policy (tri-state).

One test per policy outcome:
- `never`: branch preserved regardless of merge state.
- `delete_if_safe` with merged branch: branch deleted.
- `delete_if_safe` with unmerged branch: branch preserved.
- `always`: branch force-deleted regardless of merge state.
"""

import re
import subprocess
from pathlib import Path

import playwright.sync_api
from playwright.sync_api import Page
from playwright.sync_api import expect
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_fixed

from sculptor.testing.elements.user_config import _set_user_config_flag
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_worktree_workspace(page: Page, workspace_name: str) -> tuple[str, str]:
    """Create a worktree workspace and return `(branch_name, workspace_id)`.

    Worktree mode is the default, so no mode-selector interaction is needed.
    Waits for the branch-name preview to settle to the slug derived from
    ``workspace_name`` — otherwise the test can race with the initial
    empty-workspace-name preview (which returns a random ``<adj>-<noun>``
    slug) and pick that up instead.
    """
    open_new_workspace_form(page)
    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    add_ws_page.get_workspace_name_input().fill(workspace_name)

    branch_input = add_ws_page.get_branch_name_input()
    slug_pattern = re.sub(r"[^a-z0-9]+", "-", workspace_name.lower()).strip("-")
    expect(branch_input).to_have_value(re.compile(rf".*{re.escape(slug_pattern)}.*"))
    branch_name = branch_input.input_value()

    add_ws_page.submit_and_wait_for_chat_panel()

    expect(page).to_have_url(re.compile(r".*/ws/(ws_[a-z0-9]+)/"))
    match = re.search(r"/ws/(ws_[a-z0-9]+)/", page.url)
    assert match, f"could not extract workspace_id from URL: {page.url}"
    workspace_id = match.group(1)

    return branch_name, workspace_id


def _worktree_paths(user_repo_path: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(user_repo_path), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths: list[Path] = []
    main_path = user_repo_path.resolve()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            p = Path(line.removeprefix("worktree ").strip()).resolve()
            if p != main_path:
                paths.append(p)
    return paths


def _branch_exists(repo_path: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--list", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _commit_on_worktree(worktree_path: Path, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-C",
            str(worktree_path),
            "commit",
            "--allow-empty",
            "-m",
            message,
        ],
        check=True,
        capture_output=True,
    )


@retry(
    retry=retry_if_exception_type(playwright.sync_api.Error),
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    reraise=True,
)
def _delete_workspace_via_api(page: Page, workspace_id: str) -> None:
    # Retry on transient ECONNRESET under heavy offload-sandbox load (SCU-773).
    base_url = page.url.split("#")[0].rstrip("/")
    response = page.request.delete(f"{base_url}/api/v1/workspaces/{workspace_id}")
    assert response.ok, f"DELETE workspace failed: {response.status} {response.text()}"


def _wait_for_worktree_removed(
    page: Page, user_repo_path: Path, worktree_path: Path, timeout_ms: int = 30_000
) -> None:
    deadline_steps = timeout_ms // 100
    for _ in range(deadline_steps):
        if worktree_path.resolve() not in _worktree_paths(user_repo_path):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"worktree {worktree_path} was not removed within {timeout_ms}ms")


def _wait_for_branch_deleted(
    page: Page, repo_path: Path, branch: str, failure_message: str, timeout_ms: int = 30_000
) -> None:
    """Poll until `branch` is gone, raising `failure_message` on timeout.

    Branch deletion runs as a separate `git branch -d`/`-D` subprocess *after*
    `git worktree remove` completes, so the branch can still exist for a moment
    after the worktree disappears. `_wait_for_worktree_removed` returns as soon
    as the worktree is gone, which under load can be before branch deletion has
    run — asserting branch absence right then races. Polling here gives the
    deletion subprocess a deadline to finish before we conclude it failed.
    """
    deadline_steps = timeout_ms // 100
    for _ in range(deadline_steps):
        if not _branch_exists(repo_path, branch):
            return
        page.wait_for_timeout(100)
    raise AssertionError(failure_message)


@user_story("to preserve my worktree branch after deleting the workspace when policy is 'never'")
def test_never_policy_preserves_branch(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _set_user_config_flag(page, "workspaceBranchDeletionPolicy", "never")

    branch_name, workspace_id = _create_worktree_workspace(page, "policy-never-test")
    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]

    _commit_on_worktree(worktree_path, "unmerged commit")
    _delete_workspace_via_api(page, workspace_id)

    _wait_for_worktree_removed(page, sculptor_instance_.project_path, worktree_path)
    assert _branch_exists(sculptor_instance_.project_path, branch_name), (
        f"branch {branch_name} should be preserved under 'never' policy"
    )


@user_story("to clean up my merged branch when deleting the workspace under 'delete_if_safe'")
def test_delete_if_safe_with_merged_branch(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _set_user_config_flag(page, "workspaceBranchDeletionPolicy", "delete_if_safe")

    branch_name, workspace_id = _create_worktree_workspace(page, "policy-safe-merged")
    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]

    _delete_workspace_via_api(page, workspace_id)

    _wait_for_worktree_removed(page, sculptor_instance_.project_path, worktree_path)
    _wait_for_branch_deleted(
        page,
        sculptor_instance_.project_path,
        branch_name,
        f"branch {branch_name} should be deleted under 'delete_if_safe' when merged",
    )


@user_story("to keep my unmerged work when deleting the workspace under 'delete_if_safe'")
def test_delete_if_safe_with_unmerged_branch(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _set_user_config_flag(page, "workspaceBranchDeletionPolicy", "delete_if_safe")

    branch_name, workspace_id = _create_worktree_workspace(page, "policy-safe-unmerged")
    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]

    _commit_on_worktree(worktree_path, "unmerged commit")
    _delete_workspace_via_api(page, workspace_id)

    _wait_for_worktree_removed(page, sculptor_instance_.project_path, worktree_path)
    assert _branch_exists(sculptor_instance_.project_path, branch_name), (
        f"branch {branch_name} should be preserved because git branch -d refuses unmerged"
    )


@user_story("to force-delete even unmerged branches when policy is 'always'")
def test_always_policy_force_deletes_branch(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _set_user_config_flag(page, "workspaceBranchDeletionPolicy", "always")

    branch_name, workspace_id = _create_worktree_workspace(page, "policy-always")
    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]

    _commit_on_worktree(worktree_path, "unmerged commit")
    _delete_workspace_via_api(page, workspace_id)

    _wait_for_worktree_removed(page, sculptor_instance_.project_path, worktree_path)
    _wait_for_branch_deleted(
        page,
        sculptor_instance_.project_path,
        branch_name,
        f"branch {branch_name} should be force-deleted under 'always'",
    )
