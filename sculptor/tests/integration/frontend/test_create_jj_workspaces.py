"""Integration coverage for creating jj workspaces from the create dialog and the sidebar.

The test spawns its own instance, because it colocates its repository with jj and
leaves a `.jj` behind. jj is given to the backend as a CUSTOM path to the pinned
binary, and `jj_isolated_env` gives jj and git an empty user config and a test
identity, which the backend inherits when it is spawned.

The repository gets a bare `origin` with `main` on it, so jj's default target for
a new workspace is `main@origin`, as in a real clone.
"""

import re
from pathlib import Path

from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import add_bare_origin
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.testing.user_stories import user_story

_GIT_PROJECT_NAME = "git project"


def _use_jj_binary(factory: SculptorInstanceFactory, jj_binary: JjBinary) -> None:
    """Point the backend at the pinned jj as a CUSTOM path, before it starts."""
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    dependency_paths = config.dependency_paths.model_copy(update={"jj": str(jj_binary.path)})
    save_config(config.model_copy(update={"dependency_paths": dependency_paths}), config_path)


@user_story(
    "to create jj workspaces from the create dialog and the sidebar, while a git repository keeps its worktrees"
)
def test_create_jj_workspaces_from_the_dialog_and_the_sidebar(
    sculptor_instance_factory_: SculptorInstanceFactory,
    test_repo_factory_: TestRepoFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    _use_jj_binary(sculptor_instance_factory_, jj_binary)
    jj_repo = sculptor_instance_factory_.base_repo
    jj_repo.create_reset_and_checkout_branch("main")
    add_bare_origin(jj_repo.base_path, tmp_path / "origin.git")
    colocate_with_jj(jj_binary, jj_repo.base_path)
    jj_project_name = jj_repo.base_path.name
    git_repo = test_repo_factory_.create_repo(name=_GIT_PROJECT_NAME, branch="main")

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        repos_settings = navigate_to_settings_page(page=page).click_on_repositories()
        repos_settings.expand_repo_config()
        use_jj_switch = repos_settings.get_use_jj_for_new_workspaces_switch()
        expect(use_jj_switch).to_be_enabled()
        use_jj_switch.click()
        expect(use_jj_switch).to_be_checked()
        repos_settings.add_repo(str(git_repo.base_path.resolve()))

        # From the dialog: the repository offers a jj workspace, named by a bookmark.
        dialog = PlaywrightNewWorkspaceDialog(page)
        dialog.open_via_shortcut()
        dialog.select_project_by_name(jj_project_name)
        expect(dialog.get_mode_selector()).to_contain_text("jj workspace")
        bookmark_input = dialog.get_branch_name_input()
        expect(bookmark_input).to_have_attribute("placeholder", "Bookmark name (required)")
        dialog.get_workspace_name_input().fill("jj from dialog")
        # The repository's naming pattern may prefix the slug, as in `<user>/<slug>`.
        expect(bookmark_input).to_have_value(re.compile(r"jj-from-dialog$"), timeout=15_000)
        task_page = dialog.create_and_wait_for_chat_panel()

        expect(task_page.get_mode_badge()).to_have_text("jj")
        # The pill appears once the jj poller has read the new jj workspace, and
        # names it by its requested bookmark until the bookmark exists.
        expect(task_page.get_jj_identity_pill()).to_contain_text("jj-from-dialog", timeout=60_000)
        dialog_workspace_url = page.url

        # From the sidebar's "+": a jj workspace again, with a fresh bookmark name.
        sidebar = get_workspace_sidebar(page)
        jj_project_id = sidebar.get_repo_group_by_name(jj_project_name).get_attribute("data-project-id")
        assert jj_project_id is not None, "the jj repository's group is missing its data-project-id"
        sidebar.get_repo_add_workspace(jj_project_id).click()

        expect(sidebar.get_workspace_rows()).to_have_count(2)
        expect(page).not_to_have_url(dialog_workspace_url)
        sidebar_task_page = PlaywrightTaskPage(page=page)
        expect(sidebar_task_page.get_mode_badge()).to_have_text("jj")
        expect(sidebar_task_page.get_jj_identity_pill()).to_be_visible(timeout=60_000)

        # The git repository still creates worktrees named by a branch.
        dialog.open_via_shortcut()
        dialog.select_project_by_name(_GIT_PROJECT_NAME)
        expect(dialog.get_branch_name_input()).to_have_attribute("placeholder", "Branch name (required)")
        expect(dialog.get_mode_selector()).to_have_count(0)
        git_task_page = dialog.create_and_wait_for_chat_panel(workspace_name="git from dialog")

        expect(sidebar.get_workspace_rows()).to_have_count(3)
        expect(git_task_page.get_jj_identity_pill()).to_have_count(0)
        expect(git_task_page.get_mode_badge()).to_have_count(0)
