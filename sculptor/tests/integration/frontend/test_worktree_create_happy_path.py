"""Integration tests for the worktree workspace happy path.

Covers the three scenarios from the spec:
1. Default branch name: preview auto-fills → submit → worktree created.
2. Custom branch name: user overrides preview before submit.
3. Random slug: empty workspace name → preview uses `<user>/<adj>-<noun>`.

Worktree is the product-default mode, so these tests don't touch the mode
selector (it's hidden unless clone / in-place is enabled).
"""

import re
import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _worktree_paths(user_repo_path: Path) -> list[Path]:
    """Return all worktree paths (except the main one) for the user's repo."""
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


def _git_remotes(worktree_path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "remote"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_branch(worktree_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@user_story("to create a worktree workspace using the auto-filled branch name")
def test_worktree_create_with_default_branch_name(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)

    add_workspace.get_workspace_name_input().fill("Fix login bug")

    branch_name = add_workspace.wait_for_branch_preview(re.compile(r".*fix-login-bug.*"))
    assert branch_name.endswith("fix-login-bug"), f"expected slug to end in fix-login-bug, got: {branch_name!r}"

    add_workspace.submit_and_wait_for_chat_panel()

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert worktree_path.exists(), f"worktree path does not exist: {worktree_path}"
    assert _git_branch(worktree_path) == branch_name
    remotes = _git_remotes(worktree_path)
    assert "local" not in remotes, f"worktree should not have a local remote; got {remotes!r}"


@user_story("to create a worktree workspace with a custom branch name")
def test_worktree_create_with_custom_branch_name(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)

    add_workspace.get_workspace_name_input().fill("Some task")
    add_workspace.wait_for_branch_preview()

    custom_branch = "imbue/scu-42-custom"
    branch_input = add_workspace.get_branch_name_input()
    branch_input.fill(custom_branch)
    expect(branch_input).to_have_value(custom_branch)
    full_branch = add_workspace.read_branch_name()
    assert full_branch == custom_branch, f"expected branch {custom_branch!r}, got: {full_branch!r}"

    add_workspace.submit_and_wait_for_chat_panel()

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert _git_branch(worktree_path) == full_branch


@user_story("to not accidentally create an empty-branch workspace before the branch name finishes loading")
def test_submit_disabled_until_branch_name_preview_settles(sculptor_instance_: SculptorInstance) -> None:
    """Regression for the submit race fixed in commit 20505d4666.

    Changing the workspace name kicks off a fresh debounced branch-name preview
    fetch. While that fetch is in flight the worktree branch name is empty/stale,
    so submit must stay disabled — otherwise a click in that window lands on an
    empty branch name and `handleSubmit` silently bails, leaving the user
    thinking they created a workspace that never appears.
    """
    page = sculptor_instance_.page
    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)

    # Let the initial preview settle so submit is enabled to begin with.
    add_workspace.wait_for_branch_preview()
    expect(add_workspace.get_submit_button()).to_be_enabled()

    # Typing a new name restarts the debounced preview fetch. Submit must drop
    # back to disabled while the new branch name is loading...
    add_workspace.get_workspace_name_input().fill("Refactor the auth middleware")
    expect(add_workspace.get_submit_button()).to_be_disabled()

    # ...and only re-enable once the new branch name has landed. The backend
    # truncates the slug, so match the leading word rather than the full name.
    add_workspace.wait_for_branch_preview(re.compile(r".*refactor.*"))
    expect(add_workspace.get_submit_button()).to_be_enabled()


@user_story("to create a worktree workspace with an empty workspace name (random slug)")
def test_worktree_create_with_empty_workspace_name_random_slug(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)

    branch_name = add_workspace.wait_for_branch_preview(re.compile(r".*[a-z0-9]+-[a-z0-9]+$"))
    assert re.search(r"[a-z0-9]+-[a-z0-9]+$", branch_name), (
        f"expected a two-word random slug at the end, got: {branch_name!r}"
    )

    add_workspace.submit_and_wait_for_chat_panel()

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert _git_branch(worktree_path) == branch_name
