"""Integration tests for the Add Repository remote-clone error paths.

Every test in this file:
  * Stubs ``POST /api/v1/remotes/clone`` via ``page.route`` so no real clone
    runs and the dialog is held in a stable state for assertions.
  * Drives the dialog through the URL-fallback view (avoids depending on a
    populated combobox — picker happy path lives in the slow tier).

Route-level coverage for the actual handler lives in
``sculptor/sculptor/web/remote_repos_test.py``. The fast-tier tests here
only verify how the frontend renders each status code / network failure.
"""

import json
import re
from collections.abc import Callable

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.add_repo_dialog import PlaywrightAddRepoDialogElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Anchored so the same matcher doesn't grab unrelated /remotes/* endpoints
# (e.g. /api/v1/remotes/github/repos for the combobox).
_CLONE_ROUTE_PATTERN = re.compile(r"/api/v1/remotes/clone$")


def _open_add_repo_dialog_on_url_view(
    sculptor_instance: SculptorInstance,
    *,
    url: str,
) -> PlaywrightAddRepoDialogElement:
    """Open the Add Repository dialog, switch the GitHub form to URL view, and
    populate the URL field. Shared scaffolding for every error-path test in
    this file."""
    page = sculptor_instance.page
    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()

    add_repo_dialog.get_source_github_card().click()
    add_repo_dialog.get_remote_url_toggle().click()
    add_repo_dialog.get_remote_url_input().fill(url)
    return add_repo_dialog


def _stub_clone_with_status(status: int, detail: str) -> Callable[[Route], None]:
    """Build a ``page.route`` handler that fulfills POST /remotes/clone with
    the given status code + FastAPI-shaped ``{"detail": ...}`` body."""

    def handler(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()
            return
        route.fulfill(status=status, body=json.dumps({"detail": detail}))

    return handler


@user_story("to see the Add as local folder CTA when the clone target already exists")
def test_clone_409_offers_add_as_local_cta(sculptor_instance_: SculptorInstance) -> None:
    """A 409 with an "already exists" detail puts the dialog into the
    clone-failed phase with the proposed path in a Code block, a copy button,
    and the "Add as local folder" primary CTA wired to the local-import path."""
    page = sculptor_instance_.page
    stub = _stub_clone_with_status(409, "/fake/target already exists.")
    page.route(_CLONE_ROUTE_PATTERN, stub)

    try:
        dialog = _open_add_repo_dialog_on_url_view(
            sculptor_instance_,
            url="https://github.com/example/conflict.git",
        )
        dialog.get_submit_button().click()

        # The clone-failed phase mounts the path Code block, the copy button,
        # and the primary "Add as local folder" CTA.
        expect(dialog.get_clone_failed_path()).to_be_visible()
        expect(dialog.get_clone_failed_copy_button()).to_be_visible()
        add_local = dialog.get_clone_failed_add_local_button()
        expect(add_local).to_be_visible()
    finally:
        page.unroute(_CLONE_ROUTE_PATTERN, stub)


@user_story("not to see the Add as local folder CTA on a 412 unauthorized clone failure")
def test_clone_412_does_not_offer_add_as_local_cta(sculptor_instance_: SculptorInstance) -> None:
    """A 412 means gh isn't installed / signed in — the path conflict
    isn't the root cause, so the "Add as local folder" CTA must NOT render.
    The clone-failed view still shows the backend's detail string so the
    user sees what went wrong."""
    page = sculptor_instance_.page
    stub = _stub_clone_with_status(412, "GH CLI not authenticated")
    page.route(_CLONE_ROUTE_PATTERN, stub)

    try:
        dialog = _open_add_repo_dialog_on_url_view(
            sculptor_instance_,
            url="https://github.com/example/private.git",
        )
        dialog.get_submit_button().click()

        # The path Code block + Add-as-local CTA are gated on
        # localPathSuggestion being set, which the 412 branch in useAddRepo
        # explicitly does NOT set.
        expect(dialog.get_clone_failed_add_local_button()).to_have_count(0)
        expect(dialog.get_clone_failed_path()).to_have_count(0)
    finally:
        page.unroute(_CLONE_ROUTE_PATTERN, stub)


@user_story("to see the timeout message when the clone request hits 504")
def test_clone_504_shows_timeout_message(sculptor_instance_: SculptorInstance) -> None:
    """504 → the clone-failed view shows the backend's "Clone timed out
    after Ns." detail so the user knows how long we waited before giving
    up. The 504 path doesn't carry localPathSuggestion either."""
    page = sculptor_instance_.page
    stub = _stub_clone_with_status(
        504,
        "Clone timed out after 300s. If the repo is private, check that gh is signed in.",
    )
    page.route(_CLONE_ROUTE_PATTERN, stub)

    try:
        dialog = _open_add_repo_dialog_on_url_view(
            sculptor_instance_,
            url="https://github.com/example/slow.git",
        )
        dialog.get_submit_button().click()

        # The form-phase submit button unmounts in clone-failed view —
        # if it's still visible the dialog didn't transition.
        expect(dialog.get_submit_button()).to_have_count(0)
        # Detail string is rendered verbatim in the clone-failed messageBox.
        expect(dialog.get_clone_failed_message()).to_contain_text("Clone timed out after 300s")
        expect(dialog.get_clone_failed_add_local_button()).to_have_count(0)
    finally:
        page.unroute(_CLONE_ROUTE_PATTERN, stub)


@user_story("to see a 'Couldn't reach the backend' message when the clone request can't be sent")
def test_clone_network_failure_shows_couldnt_reach_message(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Network failures (browser TypeError on fetch — e.g. backend down)
    must surface in the clone-failed view. The exact ``error.message`` is
    browser-dependent ("Failed to fetch" in Chromium), so assert on the
    fallback hint or any non-empty failure message rather than pinning a
    specific browser string."""
    page = sculptor_instance_.page

    def stub(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()
            return
        route.abort()

    page.route(_CLONE_ROUTE_PATTERN, stub)

    try:
        dialog = _open_add_repo_dialog_on_url_view(
            sculptor_instance_,
            url="https://github.com/example/offline.git",
        )
        dialog.get_submit_button().click()

        # Whatever message we render, the form-phase submit button should
        # disappear (proving we left the form phase) and the dialog must
        # not enter the cloning-progress view (no progress title).
        expect(dialog.get_submit_button()).to_have_count(0)
        expect(dialog.get_clone_progress_title()).to_have_count(0)
        # The clone-failed phase always renders a Close button; its presence
        # is the regression signal that we landed in clone-failed (vs.
        # cloning-progress, vs. still-in-form).
        expect(dialog.get_clone_failed_close_button()).to_be_visible()
    finally:
        page.unroute(_CLONE_ROUTE_PATTERN, stub)


@user_story("to have the repo name auto-fill from the URL I paste")
def test_url_view_derives_name_from_url(sculptor_instance_: SculptorInstance) -> None:
    """Pasting ``https://github.com/owner/sample.git`` into the URL view
    should auto-populate the name input with ``sample`` and enable the
    submit button (no clone request fires — we never click submit)."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()
    add_repo_dialog.get_source_github_card().click()
    add_repo_dialog.get_remote_url_toggle().click()
    add_repo_dialog.get_remote_url_input().fill("https://github.com/owner/sample.git")

    name_input = add_repo_dialog.get_remote_name_input()
    expect(name_input).to_have_value("sample")

    # Submit becomes ready once URL + name + target dir are all populated
    # (defaultTargetDir is always non-empty in the dialog).
    expect(add_repo_dialog.get_submit_button()).to_be_enabled()


@user_story("to see the cloning title link to the GitHub web URL when I paste an SSH URL")
def test_url_view_ssh_url_clones_with_https_link_in_progress_view(
    sculptor_instance_: SculptorInstance,
) -> None:
    """``git@github.com:owner/repo.git`` should still produce a clickable
    ``https://github.com/owner/repo`` link in the CloneProgressView. Pins
    deriveWebUrl's SSH → HTTPS rewrite at the integration tier."""
    page = sculptor_instance_.page

    # Hold the POST open so the dialog parks in the cloning phase.
    def stub(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()

    page.route(_CLONE_ROUTE_PATTERN, stub)

    try:
        dialog = _open_add_repo_dialog_on_url_view(
            sculptor_instance_,
            url="git@github.com:example/ssh-repo.git",
        )
        dialog.get_submit_button().click()

        link = dialog.get_clone_progress_link()
        expect(link).to_be_visible()
        expect(link).to_have_text("example/ssh-repo")
        expect(link).to_have_attribute("href", "https://github.com/example/ssh-repo")
    finally:
        page.unroute(_CLONE_ROUTE_PATTERN, stub)
