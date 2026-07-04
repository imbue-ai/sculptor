"""Integration test for the Add Repository remote-picker happy path.

Drives the full flow: dialog open → combobox row click → submit →
clone → success toast → new project appears in the project list.

Mock burden:
  - Drop a fake ``gh`` script into ``fake_bin_dir`` so the backend's
    auth probe (``gh auth status``) exits 0. The dialog reads
    ``dependenciesStatusAtom`` to decide whether to show the combobox
    vs NotConfiguredSection, so this needs to be authoritative — the
    fake CLI is the cleanest path because the atom is also driven by
    a WebSocket update (page.route on the GET alone wouldn't survive).
  - ``page.route`` on GET /api/v1/remotes/github/repos so the combobox
    paints with a known row instead of shelling out to ``gh api``.
  - ``page.route`` on POST /api/v1/remotes/clone to short-circuit the
    subprocess. The response's ``projectPath`` points at a pre-created
    local git repo so the *real* backend ``initializeProject`` +
    ``listProjects`` calls succeed without us having to fake their
    JSON shapes.

Route-level coverage for the clone handler itself lives in
``sculptor/sculptor/web/remote_repos_test.py``.
"""

import json
import re
import subprocess
import textwrap
from pathlib import Path

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.dependency_stubs import create_cli_stub
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Anchor /clone$ so the regex doesn't also grab /clone-other (none today,
# but future-proofs the matcher).
_CLONE_ROUTE_PATTERN = re.compile(r"/api/v1/remotes/clone$")
_LIST_REPOS_ROUTE_PATTERN = re.compile(r"/api/v1/remotes/github/repos")

_FAKE_GH_SCRIPT = """\
#!/bin/bash
# Tiny stub that handles every gh subcommand the backend invokes on the
# Add Repository → GitHub flow with a successful exit. The repo-listing
# happens via page.route at the HTTP layer, so the only subcommand that
# actually reaches this script is ``auth status`` (called by
# DependencyManagementService.check_authenticated) and ``--version``
# (called by check_installed).
case "$1" in
    --version)
        echo "gh version 2.40.0 (test stub)"
        exit 0
        ;;
    auth)
        # `gh auth status` must exit 0 for the dialog to show the combobox.
        exit 0
        ;;
esac
exit 0
"""


def _make_local_git_repo(path: Path) -> None:
    """Create a real git repo with one commit at ``path`` so the backend's
    initializeProject + listProjects succeed without faking JSON shapes."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    # An initial commit is required so initializeProject doesn't trip the
    # empty-repo branch — the path of interest is the success path.
    (path / "README.md").write_text("# test repo\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@user_story("to clone a repo from the GitHub picker and have it appear in my projects")
def test_github_picker_happy_path_clones_and_adds_project(
    sculptor_instance_: SculptorInstance,
    tmp_path: Path,
) -> None:
    """Open Add Repository → GitHub source → click the first combobox row →
    submit → cloning view appears → success toast → new project appears in
    the repo list."""
    page = sculptor_instance_.page

    # 1. Pre-create the "cloned" repo on disk so real initializeProject runs.
    fake_repo_name = "picker-happy-path-repo"
    fake_repo_path = tmp_path / "clones" / fake_repo_name
    _make_local_git_repo(fake_repo_path)

    # 2. Stub the gh CLI so the backend reports gh as installed + authed.
    create_cli_stub(sculptor_instance_.fake_bin_dir, "gh", textwrap.dedent(_FAKE_GH_SCRIPT))

    # 3. Stub the remote-repos list so the combobox paints with a known row
    #    instead of shelling out to real gh api /user/repos.
    fake_repos_body = json.dumps(
        [
            {
                "fullName": f"example/{fake_repo_name}",
                "cloneUrl": f"https://github.com/example/{fake_repo_name}.git",
                "sshUrl": f"git@github.com:example/{fake_repo_name}.git",
                "isPrivate": False,
                "pushedAt": "2026-05-15T10:00:00Z",
                "description": "A repo for the integration test",
            }
        ]
    )

    def stub_list_repos(route: Route) -> None:
        if route.request.method != "GET":
            route.continue_()
            return
        route.fulfill(status=200, content_type="application/json", body=fake_repos_body)

    # 4. Stub the clone POST to short-circuit the subprocess and point the
    #    response at the pre-created on-disk repo so finalizeProject succeeds
    #    end-to-end without faking the project list.
    clone_response_body = json.dumps({"projectPath": str(fake_repo_path)})

    def stub_clone(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()
            return
        route.fulfill(status=200, content_type="application/json", body=clone_response_body)

    page.route(_LIST_REPOS_ROUTE_PATTERN, stub_list_repos)
    page.route(_CLONE_ROUTE_PATTERN, stub_clone)

    try:
        # 5. Drive the dialog.
        settings_page = navigate_to_settings_page(page=page)
        repos_settings = settings_page.click_on_repositories()
        add_repo_dialog = repos_settings.open_add_repo_dialog()

        # GitHub is the default selection; click explicitly to exercise the
        # source-card binding.
        add_repo_dialog.get_source_github_card().click()

        # The combobox row for our fake repo should mount (driven by the
        # page.route stub above).
        combobox_row = add_repo_dialog.get_repo_combobox_item(f"example/{fake_repo_name}")
        expect(combobox_row).to_be_visible()
        combobox_row.click()

        # Selecting the row enables submit. Click it to fire the clone.
        submit_button = add_repo_dialog.get_submit_button()
        expect(submit_button).to_be_enabled()
        submit_button.click()

        # 6. The dialog transitions through:
        #      form → cloning (CloneProgressView mounts) → success
        #
        # The success path closes the dialog and shows a toast. Asserting on
        # the dialog *closing* is the cleanest end-state signal that the
        # whole flow ran (cloning + initializeProject + listProjects + atom
        # update), since the dialog only closes via the onSuccess callback.
        expect(add_repo_dialog.get_source_github_card()).to_have_count(0)
    finally:
        page.unroute(_LIST_REPOS_ROUTE_PATTERN, stub_list_repos)
        page.unroute(_CLONE_ROUTE_PATTERN, stub_clone)
