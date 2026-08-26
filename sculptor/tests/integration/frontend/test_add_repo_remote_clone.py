"""Integration test for the new "Add Repository -> remote clone" flow.

Drives the Add Repository dialog through the URL-fallback path:
open the dialog, pick GitHub, switch to the URL view, paste a fake
clone URL, submit, and assert the dialog transitions out of the form
phase into the cloning-in-progress view.

The clone endpoint is stubbed at the network layer (``page.route``) so
the test never touches GitHub or the real ``gh`` / ``git`` binaries.
Route-level coverage for the actual handler lives in
``sculptor/sculptor/web/remote_repos_test.py``.
"""

import re

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Anchored so the same matcher doesn't grab unrelated /remotes/* endpoints.
_CLONE_ROUTE_PATTERN = re.compile(r"/api/v1/remotes/clone$")


@user_story("to clone a public GitHub repo by pasting its URL into Add Repository")
def test_add_repo_remote_clone_via_url_fallback(sculptor_instance_: SculptorInstance) -> None:
    """Open the Add Repository dialog -> switch to GitHub -> use URL fallback -> submit.

    Verifies:
      * SourceRadioCards renders the two options (GitHub / Local)
        with their new test IDs.
      * The URL toggle switches the GitHub form into the URL view, exposing
        the URL TextField.
      * Typing a clone URL enables the submit button.
      * Clicking submit transitions the dialog out of the form and into the
        cloning-progress view ("Cloning owner/repo…"), proving the
        form -> submit -> in-flight transition works.

    The backend POST to /api/v1/remotes/clone is intercepted via
    ``page.route`` so the clone never actually runs and the dialog stays
    in the cloning phase while the test makes its assertions.
    """
    page = sculptor_instance_.page

    # Hold the clone request open so the dialog parks in the cloning phase
    # while we assert on it. The frontend dispatches START_CLONING (which
    # swaps the form for CloneProgressView) synchronously on submit and
    # only advances past it once the POST resolves and the follow-up
    # initializeProject call fires — by never fulfilling we keep the test
    # in a stable "Cloning …" view and never actually run the clone.
    def stub_clone(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()
            return
        # No fulfill / continue: Playwright holds the request until the
        # page is torn down or the test calls page.unroute. The dialog
        # stays in the cloning phase for the duration of the assertions.

    page.route(_CLONE_ROUTE_PATTERN, stub_clone)

    try:
        settings_page = navigate_to_settings_page(page=page)
        repos_settings = settings_page.click_on_repositories()
        add_repo_dialog = repos_settings.open_add_repo_dialog()

        # Both source cards should be rendered with their new test IDs.
        expect(add_repo_dialog.get_source_github_card()).to_be_visible()
        expect(add_repo_dialog.get_source_local_card()).to_be_visible()

        # The dialog opens on the Local source; select GitHub to drive the
        # remote flow (this also exercises the ADD_REPO_SOURCE_GITHUB binding).
        add_repo_dialog.get_source_github_card().click()

        # Switch to the URL-paste view via the toggle. There are three branches
        # in the form that mount this toggle (configured search view,
        # NotConfiguredSection footer, URL view) — only one is rendered at a
        # time, so the locator resolves unambiguously regardless of which
        # branch the test environment's gh status lands us in.
        url_toggle = add_repo_dialog.get_remote_url_toggle()
        expect(url_toggle).to_be_visible()
        url_toggle.click()

        # The URL TextField appears and the submit button becomes enabled
        # once a URL (and the auto-derived repo name) are populated.
        url_input = add_repo_dialog.get_remote_url_input()
        expect(url_input).to_be_visible()
        url_input.fill("https://github.com/example/repo.git")

        submit_button = add_repo_dialog.get_submit_button()
        expect(submit_button).to_be_enabled()

        submit_button.click()

        # Submit kicks off the clone: the form is replaced with the
        # CloneProgressView's "Cloning owner/repo…" title. The form-phase
        # submit button is unmounted in this phase, which is the cleanest
        # proof that the dialog transitioned away from the form.
        clone_progress_title = add_repo_dialog.get_clone_progress_title()
        expect(clone_progress_title).to_be_visible()
        expect(clone_progress_title).to_contain_text("example/repo")
        expect(submit_button).to_have_count(0)
    finally:
        page.unroute(_CLONE_ROUTE_PATTERN, stub_clone)
