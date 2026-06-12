"""Regression tests: Settings page should not navigate away after repo changes.

Bug 1: When the user deletes a repository from the Settings > Repositories page
and other projects still remain, the app navigates away to a workspace (via
navigateToRoot()) and shows a stuck spinner. The expected behavior is to remain
on the settings page after deletion.

Bug 2: When the user adds a new repository via the "Add repository" button on
the Settings > Repositories page, the app navigates to the Open Workspace page.
The expected behavior is to remain on the settings page.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.testing.user_stories import user_story


@user_story("to stay on the settings page after deleting a repository when others remain")
def test_deleting_repo_stays_on_settings_page(
    sculptor_instance_: SculptorInstance,
    test_repo_factory_: TestRepoFactory,
) -> None:
    """After deleting a repo from Settings > Repositories when other projects
    still exist, the user should remain on the settings page.

    Steps:
    1. Add a second repo via the Settings UI so that deletion doesn't remove the last one
    2. Navigate to Settings > Repositories
    3. Delete the second repo
    4. Verify we are still on the settings page
    """
    page = sculptor_instance_.page

    # Step 1: Create a second git repo and add it via the Settings UI.
    second_repo = test_repo_factory_.create_repo(name="second-repo", branch="main")

    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()
    repos_section.add_repo(str(second_repo.repo.base_path.resolve()))

    # Step 2: Navigate to Settings > Repositories.
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()

    # Verify both repos are visible.
    repo_rows = repos_section.get_repo_rows()
    expect(repo_rows.nth(1)).to_be_visible()

    # Step 3: Delete the second repo.
    repos_section.remove_repo("second-repo")

    # Step 4: Verify we are still on the settings page (not navigated away).
    expect(settings_page.get_settings_page_locator()).to_be_visible()

    # Verify the original repo is still listed.
    expect(repo_rows.first).to_be_visible()


@user_story("to stay on the settings page after adding a new repository")
def test_adding_repo_stays_on_settings_page(
    sculptor_instance_: SculptorInstance,
    test_repo_factory_: TestRepoFactory,
) -> None:
    """After adding a repo via the 'Add repository' button on
    Settings > Repositories, the user should remain on the settings page.

    Steps:
    1. Create a new git repo to add
    2. Navigate to Settings > Repositories
    3. Click "Add repository" and add the repo via the dialog
    4. Verify we are still on the settings page with the new repo listed
    """
    page = sculptor_instance_.page

    # Step 1: Create a new git repo to add.
    new_repo = test_repo_factory_.create_repo(name="new-repo", branch="main")

    # Step 2: Navigate to Settings > Repositories.
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()

    # Step 3: Add the repo via the dialog.
    repos_section.add_repo(str(new_repo.repo.base_path.resolve()))

    # Step 4: Verify we are still on the settings page.
    expect(settings_page.get_settings_page_locator()).to_be_visible()

    # Verify the new repo appears in the list.
    repo_rows = repos_section.get_repo_rows()
    expect(repo_rows.last).to_be_visible()

    # Clean up: remove the added repo so other tests aren't affected.
    repos_section = settings_page.click_on_repositories()
    repos_section.remove_repo("new-repo")
