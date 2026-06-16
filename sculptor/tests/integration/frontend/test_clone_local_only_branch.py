"""Regression test for cloning a workspace from a local-only branch when the
source repo has remotes configured.

The bug: ``clone_strategy._remove_all_remotes`` strips the auto-created
``origin`` and *its tracking refs* before replaying source's real remotes.
When source has remotes but the requested target branch is purely local
(``refs/heads/<branch>`` with no ``refs/remotes/*/<branch>``), the clone is
left without any ref for that branch and the final ``git checkout`` fails
with ``pathspec '...' did not match any file(s) known to git``.

A ``sculptor/transfer/<desc>`` branch produced by the ``split-changes`` flow
is exactly such a local-only branch — ``git push local HEAD:sculptor/transfer/...``
lands it in the user's primary repo as ``refs/heads/sculptor/transfer/...``
with no remote-tracking counterpart.
"""

import re
import subprocess
from pathlib import Path

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import open_new_workspace_modal
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

LOCAL_ONLY_BRANCH = "sculptor/transfer/scu-521-visual-md-diffs"


def _workspace_id_from_url(page: Page) -> str:
    expect(page).to_have_url(re.compile(r".*/ws/(ws_[a-z0-9]+)/"), timeout=30_000)
    match = re.search(r"/ws/(ws_[a-z0-9]+)/", page.url)
    assert match, f"could not extract workspace_id from URL: {page.url}"
    return match.group(1)


def _clone_code_dir_for_workspace(page: Page, workspace_id: str, timeout_ms: int = 30_000) -> Path:
    base_url = page.url.split("#")[0].rstrip("/")
    for _ in range(timeout_ms // 200):
        response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert response.ok, f"GET workspace failed: {response.status} {response.text()}"
        environment_id = response.json().get("environmentId")
        if environment_id:
            return Path(environment_id) / "code"
        page.wait_for_timeout(200)
    raise AssertionError(f"workspace {workspace_id} never got an environment_id within {timeout_ms}ms")


def _wait_until_settled_then_clear(input_locator: Locator) -> None:
    expect(input_locator).to_be_visible()
    expect(input_locator).to_have_value(re.compile(r".+"))
    input_locator.fill("")
    expect(input_locator).to_have_value("")


def _git_branch(repo_path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@user_story("to start a workspace from a local-only branch even when my source repo has remotes")
def test_clone_from_local_only_branch_with_source_remotes_present(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A source with at least one remote AND a target branch that exists only
    as ``refs/heads/<branch>`` (no remote-tracking counterpart) must still be
    cloneable: the new workspace's clone should be checked out on that branch.
    """
    repo = sculptor_instance_.repo

    # Add a remote to the source repo so clone_repository takes the with-remotes
    # code path (replay source remote config + copy refs/remotes/*). The URL is
    # never fetched from, so it does not need to be reachable.
    repo.repo.run_git(("remote", "add", "origin", "/tmp/sculptor-test-nonexistent-remote"))

    # Create the local-only target branch. No `git push` — it has no
    # corresponding refs/remotes/<remote>/<branch> anywhere.
    repo.repo.run_git(("branch", LOCAL_ONLY_BRANCH))

    # Sanity: branch exists locally, has no remote-tracking ref.
    branches = repo.get_branches()
    assert LOCAL_ONLY_BRANCH in branches, f"setup failed: {LOCAL_ONLY_BRANCH!r} not in {branches}"
    remote_refs = repo.repo.run_git(("for-each-ref", "--format=%(refname)", "refs/remotes/"))
    assert LOCAL_ONLY_BRANCH not in remote_refs, (
        f"setup failed: {LOCAL_ONLY_BRANCH!r} unexpectedly has a remote-tracking ref: {remote_refs}"
    )

    page = sculptor_instance_.page
    enable_clone_workspaces(page)

    open_new_workspace_modal(page)
    add_ws_page = PlaywrightNewWorkspaceModalPage(page)
    add_ws_page.get_workspace_name_input().fill("From local-only transfer branch")

    # Worktree is the default; this test exercises CLONE behaviour, so flip
    # the mode picker over before touching the branch fields.
    add_ws_page.select_mode(ElementIDs.MODE_OPTION_CLONE)

    add_ws_page.select_branch(LOCAL_ONLY_BRANCH)

    # Wait for the auto-fill to populate the new-branch-name input (it derives
    # from the workspace name and lands asynchronously), then clear it so the
    # clone checks out the target branch directly instead of forking a new
    # branch off it. Without the wait, fill("") races against the auto-fill.
    _wait_until_settled_then_clear(add_ws_page.get_branch_name_input())

    submit_button = add_ws_page.get_submit_button()
    expect(submit_button).to_be_enabled()
    submit_button.click()

    task_page = PlaywrightTaskPage(page)
    expect(task_page.get_chat_panel()).to_be_visible(timeout=60_000)

    workspace_id = _workspace_id_from_url(page)
    clone_path = _clone_code_dir_for_workspace(page, workspace_id)
    assert _git_branch(clone_path) == LOCAL_ONLY_BRANCH, (
        f"expected clone checked out on {LOCAL_ONLY_BRANCH!r}, got {_git_branch(clone_path)!r}"
    )
