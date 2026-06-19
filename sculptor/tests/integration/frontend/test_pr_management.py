"""Integration tests for the PR management feature."""

from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to not see PR management UI on a non-GitLab workspace")
def test_banner_hides_pr_ui_for_non_gitlab_origin(sculptor_instance_: SculptorInstance) -> None:
    """Verify the banner does NOT show PR elements for non-GitLab origins."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, "say hello")

    # Non-GitLab workspace should not show PR button or target branch selector
    expect(task_page.get_pr_button_create()).not_to_be_visible()
    expect(task_page.get_target_branch_selector()).not_to_be_visible()


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
