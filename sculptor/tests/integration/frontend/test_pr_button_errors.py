"""Integration tests for PR button error reporting.

Tests verify that when the gh/glab CLI is missing, returns auth errors,
or returns access errors, the frontend shows the ErrorPrButton with the
appropriate message.  Fake CLI scripts are dropped into
``sculptor_instance_.fake_bin_dir`` (always on the backend subprocess's
PATH); within a test the fake CLI's behavior is switched via a control
file that the script reads at invocation time.

The "missing CLI" group still uses ``sculptor_instance_factory_`` because
it needs PATH to *exclude* gh/glab entirely, which requires a dedicated
backend process with a filtered PATH.
"""

import os
import textwrap
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.dependency_stubs import create_cli_stub
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import delete_all_workspaces_via_ui
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_FAKE_GITHUB_REMOTE = "https://github.com/test-org/test-repo.git"
_FAKE_GITLAB_REMOTE = "https://gitlab.com/test-group/test-repo.git"


def _set_remote(instance: SculptorInstance, url: str) -> None:
    """Replace the repo's origin with the given URL and reload the SPA."""
    repo = instance.repo
    try:
        repo.repo.run_git(("remote", "remove", "origin"))
    except Exception:
        pass
    repo.repo.run_git(("remote", "add", "origin", url))
    full_spa_reload(instance.page)


def _create_fake_cli(directory: Path, name: str, script: str) -> None:
    """Create a fake CLI script in the given directory."""
    create_cli_stub(directory, name, textwrap.dedent(script))


def _start_task_and_wait_for_pr_status(page: Page, prompt: str, expected_button: str) -> PlaywrightTaskPage:
    """Start a task and wait for the *specific* expected PR button to appear.

    Clone-mode workspaces are initialized on the target branch, so the first
    PR poll runs while ``current_branch == target_branch`` and the backend
    returns ``pr_state="none"`` with no error_category — which renders as the
    "Create PR" button. The agent's ``git checkout -b <agent_branch>`` runs
    afterwards, the next branch-change-triggered poll invokes ``gh``, and the
    UI transitions to the real terminal state.

    Waiting on any-of-three buttons would return on the transient "Create PR"
    and race the follow-up ``expect(...)`` against the second poll. Pass the
    specific element id the test expects so we block until the UI has settled
    on it.
    """
    task_page = start_task_and_wait_for_ready(page, prompt)
    # The backend poll cadence on slow CI runners (e.g. offload) plus the
    # clone-on-target-branch transient means the initial PR button can take
    # a non-trivial amount of time to reach its final state — give it a
    # generous budget before we conclude the status never arrived.
    task_page.wait_for_pr_button(expected_button)
    return task_page


def _expand_details_and_verify(task_page: PlaywrightTaskPage, expected_substring: str) -> None:
    """Click the Details summary to expand it and verify the error message."""
    task_page.get_pr_button_error_details().click()
    popover = task_page.get_pr_button_error_popover()
    expect(popover).to_contain_text(expected_substring)


def _set_path_without_cli(factory: SculptorInstanceFactory, tmp_path: Path) -> None:
    """Set PATH to exclude real gh/glab CLIs while keeping python and git available."""
    cli_names = {"gh", "glab"}
    current_path = os.environ.get("PATH", "")
    filtered_dirs = [d for d in current_path.split(":") if not any((Path(d) / name).exists() for name in cli_names)]
    factory._delegate.environment["PATH"] = ":".join(filtered_dirs)


def _cleanup_workspaces(instance: SculptorInstance) -> None:
    """Delete all workspaces and navigate to the add-workspace page for the next scenario.

    `delete_all_workspaces_via_ui` ends on /home (where Phase 2 finds the
    closed-workspace rows). With sculptor-tabs MRU restoration, leaving the
    user on /home means the next `_set_remote` full reload's rootLoader
    sees __home__ as the active tab and redirects there — and the test
    expects to land on /ws/new instead. Explicitly navigate to the
    add-workspace page to set the active tab before any subsequent reload.
    """
    delete_all_workspaces_via_ui(instance.page)
    navigate_to_add_workspace_page(instance.page)


def _assert_error_button_with_popover(
    task_page: PlaywrightTaskPage,
    *,
    button_label: str,
    popover_text: str,
    details_text: str,
    is_actionable: bool = True,
) -> None:
    """Assert the error button is visible, click it, and verify the popover content."""
    error_button = task_page.get_pr_button_error()
    expect(error_button).to_be_visible()
    expect(error_button).to_contain_text(button_label)
    expect(error_button).to_have_attribute("data-error-actionable", str(is_actionable).lower())

    error_button.click()
    popover = task_page.get_pr_button_error_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text(popover_text)
    _expand_details_and_verify(task_page, details_text)


# ---------------------------------------------------------------------------
# Group 1: CLI missing (no gh/glab on PATH) — one spawn, two scenarios
# ---------------------------------------------------------------------------


@user_story("to see an error when gh/glab CLI is not installed")
def test_cli_missing_shows_error_for_github_and_gitlab(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    """When gh/glab is not on PATH, the error button should show 'CLI not installed'."""
    _set_path_without_cli(sculptor_instance_factory_, tmp_path)

    with sculptor_instance_factory_.spawn_instance() as instance:
        # --- GitHub ---
        _set_remote(instance, _FAKE_GITHUB_REMOTE)
        task_page = _start_task_and_wait_for_pr_status(
            instance.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
        )

        _assert_error_button_with_popover(
            task_page,
            button_label="Create PR",
            popover_text="GitHub CLI not installed",
            details_text="gh CLI not found in PATH",
        )
        popover = task_page.get_pr_button_error_popover()
        expect(popover).to_contain_text("brew install gh")

        # --- GitLab ---
        _cleanup_workspaces(instance)
        _set_remote(instance, _FAKE_GITLAB_REMOTE)
        task_page = _start_task_and_wait_for_pr_status(
            instance.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
        )

        _assert_error_button_with_popover(
            task_page,
            button_label="Create MR",
            popover_text="GitLab CLI not installed",
            details_text="glab CLI not found in PATH",
        )
        popover = task_page.get_pr_button_error_popover()
        expect(popover).to_contain_text("brew install glab")


# ---------------------------------------------------------------------------
# Group 2: GitHub error variants — one spawn, mode-switching fake gh
# ---------------------------------------------------------------------------

_FAKE_GH_SCRIPT = """\
#!/bin/bash
MODE=$(cat "{mode_file}")
case "$MODE" in
    auth)
        echo "not logged into any github hosts. Run 'gh auth login'" >&2
        exit 1
        ;;
    403)
        echo "HTTP 403: Resource not accessible by integration (403 forbidden)" >&2
        exit 1
        ;;
    dns)
        echo "could not resolve host: api.github.com" >&2
        exit 1
        ;;
esac
"""


@user_story("to see errors when gh CLI reports problems")
def test_github_cli_error_variants(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Auth error, 403, and DNS error each show the correct error in the PR button."""
    mode_file = tmp_path / "gh_mode"
    _create_fake_cli(sculptor_instance_.fake_bin_dir, "gh", _FAKE_GH_SCRIPT.format(mode_file=mode_file))
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    # --- Auth error ---
    mode_file.write_text("auth")
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
    )

    _assert_error_button_with_popover(
        task_page,
        button_label="Create PR",
        popover_text="GitHub authentication required",
        details_text="not logged into any github hosts",
    )
    popover = task_page.get_pr_button_error_popover()
    expect(popover).to_contain_text("gh auth login")

    # --- 403 Forbidden ---
    _cleanup_workspaces(sculptor_instance_)
    mode_file.write_text("403")
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
    )

    _assert_error_button_with_popover(
        task_page,
        button_label="Create PR",
        popover_text="Repository access denied",
        details_text="403 forbidden",
    )

    # --- DNS error ---
    _cleanup_workspaces(sculptor_instance_)
    mode_file.write_text("dns")
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
    )

    _assert_error_button_with_popover(
        task_page,
        button_label="Create PR",
        popover_text="Can't connect to GitHub",
        details_text="could not resolve host: api.github.com",
    )


# ---------------------------------------------------------------------------
# Group 3: GitHub happy paths — one spawn, mode-switching fake gh
# ---------------------------------------------------------------------------

_FAKE_GH_HAPPY_SCRIPT = """\
#!/bin/bash
MODE=$(cat "{mode_file}")
case "$MODE" in
    no_pr)
        # Disambiguate per-subcommand so the backend's follow-up calls
        # (status rollup / reviews / reviewThreads) don't parse "[]" as
        # invalid JSON for the object-shaped responses they expect.
        if [[ "$*" == *"pr list"* ]]; then
            echo "[]"
        elif [[ "$*" == *"statusCheckRollup"* ]]; then
            echo '{{"statusCheckRollup": []}}'
        elif [[ "$*" == *"reviews"* ]]; then
            echo '{{"reviews": []}}'
        elif [[ "$*" == *"reviewThreads"* ]]; then
            echo '{{"reviewThreads": []}}'
        else
            echo "{{}}"
        fi
        ;;
    open_pr)
        if [[ "$*" == *"pr list"* ]]; then
            echo '[{{"number": 42, "title": "Test PR", "url": "https://github.com/test/repo/pull/42", "baseRefName": "main", "state": "OPEN"}}]'
        elif [[ "$*" == *"statusCheckRollup"* ]]; then
            echo '{{"statusCheckRollup": []}}'
        elif [[ "$*" == *"reviews"* ]]; then
            echo '{{"reviews": []}}'
        elif [[ "$*" == *"reviewThreads"* ]]; then
            echo '{{"reviewThreads": []}}'
        fi
        ;;
esac
"""


@user_story("to see correct PR button states when gh CLI works")
def test_github_happy_paths(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """No-PR and open-PR scenarios each show the correct button state."""
    mode_file = tmp_path / "gh_mode"
    _create_fake_cli(sculptor_instance_.fake_bin_dir, "gh", _FAKE_GH_HAPPY_SCRIPT.format(mode_file=mode_file))
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    # --- No PR exists → Create PR button ---
    mode_file.write_text("no_pr")
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_CREATE
    )

    create_button = task_page.get_pr_button_create()
    expect(create_button).to_be_visible()
    expect(create_button).to_contain_text("Create PR")

    # --- Open PR exists → Open PR button ---
    _cleanup_workspaces(sculptor_instance_)
    mode_file.write_text("open_pr")
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_OPEN
    )

    open_button = task_page.get_pr_button_open()
    expect(open_button).to_be_visible()
    expect(open_button).to_contain_text("PR #42")


# ---------------------------------------------------------------------------
# Group 4: GitLab error variants — one spawn, mode-switching fake glab
# ---------------------------------------------------------------------------

_FAKE_GLAB_SCRIPT = """\
#!/bin/bash
MODE=$(cat "{mode_file}")
case "$MODE" in
    auth)
        echo "not logged in. Run 'glab auth login'" >&2
        exit 1
        ;;
    dns)
        echo "could not resolve host: gitlab.com" >&2
        exit 1
        ;;
esac
"""


@user_story("to see errors when glab CLI reports problems")
def test_gitlab_cli_error_variants(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Auth error and DNS error each show the correct error in the PR/MR button."""
    mode_file = tmp_path / "glab_mode"
    _create_fake_cli(sculptor_instance_.fake_bin_dir, "glab", _FAKE_GLAB_SCRIPT.format(mode_file=mode_file))
    _set_remote(sculptor_instance_, _FAKE_GITLAB_REMOTE)

    # --- Auth error ---
    mode_file.write_text("auth")
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
    )

    _assert_error_button_with_popover(
        task_page,
        button_label="Create MR",
        popover_text="GitLab authentication required",
        details_text="not logged in",
    )
    popover = task_page.get_pr_button_error_popover()
    expect(popover).to_contain_text("glab auth login")

    # --- DNS error ---
    _cleanup_workspaces(sculptor_instance_)
    mode_file.write_text("dns")
    _set_remote(sculptor_instance_, _FAKE_GITLAB_REMOTE)
    task_page = _start_task_and_wait_for_pr_status(
        sculptor_instance_.page, "say hello", expected_button=ElementIDs.PR_BUTTON_ERROR
    )

    _assert_error_button_with_popover(
        task_page,
        button_label="Create MR",
        popover_text="Can't connect to GitLab",
        details_text="could not resolve host: gitlab.com",
    )
