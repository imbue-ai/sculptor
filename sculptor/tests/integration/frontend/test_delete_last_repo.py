"""Integration tests for deleting the last repository.

When a user deletes their only remaining repository, the app should redirect
them back to the onboarding wizard at the ADD_REPO step so they can add a
new repo.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.onboarding_page import PlaywrightOnboardingPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@user_story("to be redirected to onboarding after deleting my last repo")
def test_deleting_last_repo_shows_onboarding_add_repo_step(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """After deleting the only remaining repo, the onboarding ADD_REPO step should appear.

    Steps:
    1. Navigate to Settings > Repositories
    2. Delete the only repo (the remove button should be enabled)
    3. Confirm the deletion
    4. The onboarding wizard should appear at the ADD_REPO step
    """
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page

        settings_page = navigate_to_settings_page(page=page)
        repos_settings = settings_page.click_on_repositories()

        remove_button = repos_settings.get_first_repo_remove_button()
        expect(remove_button).to_be_enabled()

        repos_settings.remove_first_repo()

        onboarding_page = PlaywrightOnboardingPage(page)
        add_repo_step = onboarding_page.get_add_repo_step()
        expect(add_repo_step).to_be_visible()
