"""Integration tests for the PR management feature."""

from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A Bitbucket origin is neither GitHub nor GitLab, so it exercises the
# "unrecognized host" path that used to hide the target-branch selector.
_BITBUCKET_REMOTE = "https://bitbucket.org/test-org/test-repo.git"


def _set_remote(instance: SculptorInstance, url: str) -> None:
    """Replace the repo's origin with the given URL and reload the SPA."""
    repo = instance.repo
    try:
        repo.repo.run_git(("remote", "remove", "origin"))
    except Exception:
        pass
    repo.repo.run_git(("remote", "add", "origin", url))
    full_spa_reload(instance.page)


@user_story("to not see PR management UI on a non-GitLab workspace")
def test_banner_hides_pr_ui_for_non_gitlab_origin(sculptor_instance_: SculptorInstance) -> None:
    """Verify the banner does NOT show the PR button for non-GitHub/GitLab origins.

    PR/MR creation requires a GitHub or GitLab provider, so the PR button stays
    hidden. The target-branch selector is host-agnostic and remains visible — it
    is covered by ``test_banner_shows_target_branch_selector_for_non_github_gitlab_origin``.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, "say hello")

    # Non-GitHub/GitLab workspace should not show the PR button.
    expect(task_page.get_pr_button_create()).not_to_be_visible()


@user_story("to choose a target branch on a repo whose origin is not GitHub or GitLab")
def test_banner_shows_target_branch_selector_for_non_github_gitlab_origin(
    sculptor_instance_: SculptorInstance,
) -> None:
    """SCU-1526: the target-branch selector must be available regardless of git host.

    A Bitbucket origin (neither GitHub nor GitLab) used to hide the selector
    entirely, leaving the merge target fixed and uneditable. The selector is
    host-agnostic, so it should render and open for any repo.
    """
    page = sculptor_instance_.page
    _set_remote(sculptor_instance_, _BITBUCKET_REMOTE)

    task_page = start_task_and_wait_for_ready(page, "say hello")

    # The selector renders so the user can see the current target...
    selector = task_page.get_target_branch_selector()
    expect(selector).to_be_visible()

    # ...and it is a real, interactive dropdown (opens a branch search box),
    # not a fixed, uneditable label.
    selector.click()
    expect(page.get_by_placeholder("Search branches...")).to_be_visible()
    page.keyboard.press("Escape")

    # PR/MR creation still requires a GitHub or GitLab provider, so the PR
    # button stays hidden for other hosts.
    expect(task_page.get_pr_button_create()).not_to_be_visible()


@user_story("to configure PR settings in the Settings page")
def test_settings_git_section(sculptor_instance_: SculptorInstance) -> None:
    """Navigate to Settings > Git, verify fields, edit and save."""
    page = sculptor_instance_.page
    config_path = sculptor_instance_.sculptor_folder / "internal" / "config.toml"

    settings_page = navigate_to_settings_page(page=page)
    git_section = settings_page.click_on_git()

    expect(git_section.get_creation_prompt_textarea()).to_be_visible()
    expect(git_section.get_poll_interval_input()).to_be_visible()
    expect(git_section.get_default_target_branch_input()).to_be_visible()

    git_section.set_default_target_branch("develop")

    toast = settings_page.get_toast()
    expect(toast).to_be_visible()

    config = load_config(config_path)
    assert config.pr_default_target_branch == "develop"
