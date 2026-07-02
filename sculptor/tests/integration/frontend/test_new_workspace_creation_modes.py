"""Integration tests for new-workspace branch/mode behaviour via the modal (WSC-06/08/09/10).

Migrates the real assertion bodies from the /ws/new-page suites —
test_branch_name_collisions.py, test_clone_mode_branch_name.py,
test_worktree_create_happy_path.py, and test_worktree_edge_cases.py — but drives
them through the new-workspace dialog instead of the page. The git-state checks
(worktree metadata, clone checkout branch) are unchanged; only the surface that
fills the form moves to the modal.

The modal's entry points are only live once a workspace exists (the empty
first-run state disables Cmd+K and the global shortcuts), so each test seeds one
worktree workspace first and then opens the dialog with Cmd/Meta+T.
"""

import re
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.elements.user_config import enable_in_place_workspaces
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

COLLIDING_BRANCH = "alice/conflicting"


def _unique_token() -> str:
    """A short unique token so each test's branch name is distinct.

    The shared instance deletes WORKSPACES between tests but their git branches
    linger, so a fixed workspace name would auto-generate a colliding branch on the
    second test (a 409 the modal surfaces as an inline error, not a create) — unique
    names keep each create collision-free.
    """
    return uuid.uuid4().hex[:8]


def _seed_one_workspace(page: Page) -> None:
    """Create one worktree workspace so the dialog entry points are live.

    Uses the helper's auto-unique workspace name (no fixed name) so the seed's branch
    can't collide with a prior test's lingering branch on the shared instance.
    """
    start_task_and_wait_for_ready(page, prompt="Say hello")


def _open_dialog(page: Page) -> PlaywrightNewWorkspaceDialog:
    dialog = PlaywrightNewWorkspaceDialog(page)
    dialog.open_via_shortcut()
    return dialog


# -- Git-state helpers (ported verbatim from the /ws/new-page suites) --


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


def _git_branch(repo_path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _branch_exists(repo_path: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--list", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _no_new_worktree_metadata(repo_path: Path) -> bool:
    worktrees_dir = repo_path / ".git" / "worktrees"
    if not worktrees_dir.is_dir():
        return True
    return not any(worktrees_dir.iterdir())


def _workspace_id_from_url(page: Page) -> str:
    expect(page).to_have_url(re.compile(r".*/ws/(ws_[a-z0-9]+)/"))
    match = re.search(r"/ws/(ws_[a-z0-9]+)/", page.url)
    assert match, f"could not extract workspace_id from URL: {page.url}"
    return match.group(1)


def _clone_code_dir_for_workspace(page: Page, base_url: str, workspace_id: str, timeout_ms: int = 30_000) -> Path:
    for _ in range(timeout_ms // 200):
        response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert response.ok, f"GET workspace failed: {response.status} {response.text()}"
        environment_id = response.json().get("environmentId")
        if environment_id:
            return Path(environment_id) / "code"
        page.wait_for_timeout(200)
    raise AssertionError(f"workspace {workspace_id} never got an environment_id within {timeout_ms}ms")


@pytest.fixture
def colliding_branch(sculptor_instance_: SculptorInstance) -> Iterator[str]:
    """Pre-create a branch in the fixture repo so the test can collide with it."""
    repo_path = sculptor_instance_.project_path
    subprocess.run(
        ["git", "-C", str(repo_path), "branch", COLLIDING_BRANCH],
        check=True,
        capture_output=True,
    )
    try:
        yield COLLIDING_BRANCH
    finally:
        subprocess.run(
            ["git", "-C", str(repo_path), "branch", "-D", COLLIDING_BRANCH],
            capture_output=True,
            check=False,
        )


# -- WSC-06: branch pill (sanitize / shuffle / stable error slot) --


@user_story("to have my typed branch name sanitized so the pill only ever shows a valid git ref")
def test_branch_name_is_sanitized(sculptor_instance_: SculptorInstance) -> None:
    """Typing characters git rejects strips them out of the branch pill (WSC-06).

    Whitespace collapses to a hyphen and reserved ref characters are dropped, so
    the field can never present a name the create call would reject.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    branch_input = dialog.get_branch_name_input()
    expect(branch_input).to_be_visible()

    branch_input.fill("feature branch:with*bad?chars")
    # Spaces → hyphen; ":", "*", "?" dropped.
    expect(branch_input).to_have_value("feature-branchwithbadchars")


@user_story("to re-roll the auto-filled branch name with the shuffle button")
def test_branch_name_shuffle_rerolls_name(sculptor_instance_: SculptorInstance) -> None:
    """Shuffle generates a fresh auto-filled branch name (WSC-06)."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    branch_input = dialog.get_branch_name_input()
    # Empty title → the preview is a random `<user>/<adj>-<noun>` slug.
    expect(branch_input).to_have_value(re.compile(r".*[a-z0-9]+-[a-z0-9]+$"))
    first_name = branch_input.input_value()

    dialog.get_branch_shuffle_button().click()
    expect(branch_input).not_to_have_value(first_name)


@user_story("to see a clear error when my branch name collides with an existing branch")
def test_worktree_collision_blocks_creation(sculptor_instance_: SculptorInstance, colliding_branch: str) -> None:
    """A colliding branch name surfaces the inline error and blocks create (WSC-06/08).

    Migrated from test_branch_name_collisions.py::test_worktree_mode_collision_blocks_creation,
    driven through the modal. The git-state check (no stale worktree metadata) is
    unchanged. The seed workspace already created one worktree, so the check is
    scoped to confirm the BLOCKED create added none beyond it.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)
    seed_worktree_count = len(_worktree_paths(sculptor_instance_.project_path))

    dialog = _open_dialog(page)
    dialog.get_workspace_name_input().fill("collide")

    branch_input = dialog.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"))
    branch_input.fill(colliding_branch)

    collision_error = dialog.get_branch_name_collision_error()
    expect(collision_error).to_be_visible()
    expect(collision_error).to_contain_text(colliding_branch)
    expect(collision_error).to_contain_text("already exists")

    # Create is blocked: the inline collision disables the Create button, and a
    # keyboard submit attempt is a guarded no-op — the dialog stays open and no
    # new worktree appears. (The backend 409 re-check remains as a race safety
    # net but is unreachable through the UI once the inline check resolves.)
    expect(dialog.get_create_button()).to_be_disabled()
    page.keyboard.press(f"{get_playwright_modifier_key()}+Enter")
    expect(dialog.get_dialog()).to_be_visible()
    expect(page).to_have_url(re.compile(r".*/ws/(ws_[a-z0-9]+)/"))

    after_worktree_count = len(_worktree_paths(sculptor_instance_.project_path))
    assert after_worktree_count == seed_worktree_count, (
        "a failed collision submit should not create an additional worktree"
    )


# -- WSC-09: worktree happy path (auto / custom / random slug) --


@user_story("to create a worktree workspace using the auto-filled branch name")
def test_worktree_create_with_default_branch_name(sculptor_instance_: SculptorInstance) -> None:
    """Migrated from test_worktree_create_happy_path.py, driven through the modal."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    # A base name unique to this test, so its auto-branch can't collide with another
    # test's lingering branch on the shared instance.
    dialog.get_workspace_name_input().fill("Fix login bug")
    branch_input = dialog.get_branch_name_input()
    expect(branch_input).to_have_value(re.compile(r".*fix-login-bug$"))
    branch_name = branch_input.input_value()

    dialog.create_and_wait_for_chat_panel()

    # The newest worktree carries the created branch.
    matching = [p for p in _worktree_paths(sculptor_instance_.project_path) if _git_branch(p) == branch_name]
    assert matching, f"no worktree on branch {branch_name!r}"


@user_story("to create a worktree workspace with a custom branch name")
def test_worktree_create_with_custom_branch_name(sculptor_instance_: SculptorInstance) -> None:
    """Migrated from test_worktree_create_happy_path.py, driven through the modal."""
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    dialog.get_workspace_name_input().fill("Some task")
    branch_input = dialog.get_branch_name_input()
    expect(branch_input).to_have_value(re.compile(r".+"))

    custom_name = f"alice/scu-42-{_unique_token()}"
    branch_input.fill(custom_name)
    expect(branch_input).to_have_value(custom_name)

    dialog.create_and_wait_for_chat_panel()

    matching = [p for p in _worktree_paths(sculptor_instance_.project_path) if _git_branch(p) == custom_name]
    assert matching, f"no worktree on branch {custom_name!r}"


# -- WSC-10: source-branch selection --


@user_story("to create a workspace from a non-default source branch")
def test_create_from_non_default_source_branch(sculptor_instance_: SculptorInstance) -> None:
    """Selecting a source branch in the dialog branches the worktree off it (WSC-10).

    The fixture repo carries a ``main`` branch in addition to the default
    ``testing`` checkout; selecting it changes the source the new worktree
    branches from.
    """
    page = sculptor_instance_.page
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    dialog.get_workspace_name_input().fill("from-main")
    expect(dialog.get_branch_name_input()).to_have_value(re.compile(r".+"))

    dialog.select_branch("main")
    expect(dialog.get_branch_selector()).to_contain_text("main")

    dialog.create_and_wait_for_chat_panel()
    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible()


# -- WSC-08: mode selector (worktree default; clone/in-place behind flags) --


@user_story("to only see the worktree mode by default, with clone/in-place gated behind flags")
def test_mode_selector_gates_optional_modes(sculptor_instance_: SculptorInstance) -> None:
    """The mode selector is hidden by default and lists only the enabled opt-in modes (WSC-08).

    Migrated from test_worktree_edge_cases.py::test_clone_mode_hidden_when_flag_off,
    driven through the modal. Worktree is always the default; the selector only
    renders once an opt-in mode is enabled, and then lists exactly the enabled
    ones.
    """
    page = sculptor_instance_.page
    # Enable in-place only — the selector should show Worktree + In-place, no Clone.
    enable_in_place_workspaces(page)
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    dialog.get_mode_selector().click()
    expect(dialog.get_mode_option_worktree()).to_be_visible()
    expect(dialog.get_mode_option_in_place()).to_be_visible()
    expect(dialog.get_mode_option_clone()).to_have_count(0)
    page.keyboard.press("Escape")

    # Enabling clone too (reloads the page) makes the Clone option appear.
    enable_clone_workspaces(page)
    dialog = _open_dialog(page)
    dialog.get_mode_selector().click()
    expect(dialog.get_mode_option_clone()).to_be_visible()
    page.keyboard.press("Escape")


@user_story("to clone a repo and work on a new branch using the auto-filled name")
def test_clone_mode_kept_branch_name_creates_new_branch(sculptor_instance_: SculptorInstance) -> None:
    """Migrated from test_clone_mode_branch_name.py, driven through the modal (WSC-08).

    Clone is opt-in: enable the flag, seed a worktree workspace, then create a
    CLONE workspace from the dialog keeping the auto-filled branch name. The
    git-state check (the clone checks out the new branch) is unchanged.
    """
    page = sculptor_instance_.page
    enable_clone_workspaces(page)
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    # A base name unique to this test so its auto-branch is distinct on the shared
    # instance (the workspace-name suffix is dropped from the slug, so use distinct words).
    dialog.get_workspace_name_input().fill("Clone new feature")
    dialog.select_mode(ElementIDs.MODE_OPTION_CLONE)

    branch_input = dialog.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".*clone-new-feature.*"))
    expected_branch = branch_input.input_value()

    dialog.create_and_wait_for_chat_panel()

    workspace_id = _workspace_id_from_url(page)
    clone_path = _clone_code_dir_for_workspace(page, sculptor_instance_.backend_api_url, workspace_id)
    assert _git_branch(clone_path) == expected_branch
    assert _branch_exists(clone_path, expected_branch)


@user_story("to clone a repo and work on the base branch directly by clearing the branch-name field")
def test_clone_mode_cleared_branch_checks_out_base(sculptor_instance_: SculptorInstance) -> None:
    """Migrated from test_clone_mode_branch_name.py, driven through the modal (WSC-08/10).

    In CLONE mode the branch field is optional: clearing it checks out the base
    branch directly rather than creating a new branch. The git-state checks are
    unchanged.
    """
    page = sculptor_instance_.page
    enable_clone_workspaces(page)
    _seed_one_workspace(page)

    dialog = _open_dialog(page)
    dialog.get_workspace_name_input().fill("Clear branch work")
    dialog.select_mode(ElementIDs.MODE_OPTION_CLONE)

    branch_input = dialog.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".*clear-branch-work.*"))
    branch_input.fill("")
    expect(branch_input).to_have_value("")

    dialog.create_and_wait_for_chat_panel()

    workspace_id = _workspace_id_from_url(page)
    clone_path = _clone_code_dir_for_workspace(page, sculptor_instance_.backend_api_url, workspace_id)
    current = _git_branch(clone_path)
    assert current in {"main", "master", "testing"}, f"unexpected base branch: {current!r}"
    assert not _branch_exists(clone_path, "test/some-work"), "clearing the branch field should not create a new branch"
