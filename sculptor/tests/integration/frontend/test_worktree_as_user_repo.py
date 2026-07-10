"""Integration tests for registering a git worktree as the Sculptor user repo.

Scenario: a user runs Sculptor (e.g. via ``just start``) from inside a git
worktree. That Sculptor instance auto-registers its cwd — the worktree —
as a project. Today, creating a clone workspace from that project fails
because ``git clone --reference <worktree>`` is rejected by upstream git
("reference repository ... as a linked checkout is not supported yet").

The fix canonicalises worktree paths to their parent repo at registration
time, so the registered project points at a real repository and downstream
operations (clone, branch listing, etc.) work normally.
"""

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.testing.user_stories import user_story


def _add_repo_via_settings(page: Page, repo_path: Path) -> None:
    """Add a repository via the Settings > Repositories UI dialog."""
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()
    repos_section.add_repo(str(repo_path.resolve()))


@user_story("to register a worktree as a repo and create a clone workspace from it")
def test_clone_workspace_from_worktree_user_repo(
    sculptor_instance_: SculptorInstance,
    test_repo_factory_: TestRepoFactory,
    tmp_path: Path,
) -> None:
    """Registering a worktree path canonicalises to the parent repo, and clone workspaces work.

    Before the fix, ``git clone --reference <worktree>`` fails with
    ``fatal: reference repository ... as a linked checkout is not supported yet``,
    so creating a clone workspace from a worktree-shaped repo errors out.
    After the fix, the worktree is resolved to its parent at registration
    time and the clone uses the parent as its --reference.
    """
    parent_name = "worktree_parent_repo"
    main_repo = test_repo_factory_.create_repo(name=parent_name, branch="main")

    worktree_path = tmp_path / "wt_branch"
    main_repo.repo.run_git(("worktree", "add", str(worktree_path), "-b", "wt_branch"))
    # Sanity-check: a worktree's .git is a gitfile pointer, not a directory.
    # If this ever stops being true we are no longer testing the bug repro.
    assert (worktree_path / ".git").is_file()

    page = sculptor_instance_.page
    _add_repo_via_settings(page, worktree_path)

    # The registered project should be canonicalised to the parent repo's
    # name, not the worktree directory's name.
    open_new_workspace_form(page)
    add_workspace_page = PlaywrightAddWorkspacePage(page)
    add_workspace_page.select_project_by_name(parent_name)

    # Creating a clone workspace from the worktree-derived repo must succeed.
    task_page = start_task_and_wait_for_ready(
        page,
        prompt="hello world",
        workspace_name="Clone From Worktree",
    )
    expect(task_page.get_chat_panel()).to_be_visible()
