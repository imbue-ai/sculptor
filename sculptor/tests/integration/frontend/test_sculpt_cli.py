"""Integration tests for the sculpt CLI against a running Sculptor backend.

These tests verify that:
- Users can interact with Sculptor via the sculpt CLI and see results in the UI
- Users can interact with Sculptor via the UI and see results via the sculpt CLI
- The CLI's JSON output accurately reflects backend state

Each test uses the shared sculptor_instance_ fixture, which provides a running
Sculptor backend and a Playwright browser page.  The sculpt CLI is invoked as a
subprocess pointed at the backend's URL so its stdout is isolated from the
backend's logging.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import playwright.sync_api
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _get_project_id(instance: SculptorInstance, retries: int = 3) -> str:
    """Fetch the active project ID from the running backend with retries.

    Retries on transient connection errors (e.g. ECONNRESET) that can
    occur under heavy CI load.
    """
    base_url = instance.backend_api_url.rstrip("/")
    for attempt in range(retries):
        try:
            response = instance.page.request.get(f"{base_url}/api/v1/projects/active")
            projects = response.json()
            return projects[0]["objectId"] if projects else ""
        except playwright.sync_api.Error:
            if attempt == retries - 1:
                raise
            instance.page.wait_for_timeout(200)
    return ""  # unreachable, but satisfies type checker


def _run_sculpt(instance: SculptorInstance, args: list[str]) -> tuple[int, str]:
    """Invoke the sculpt CLI as a subprocess and return (exit_code, stdout).

    Automatically injects --base-url and --json flags, and sets the
    SCULPT_PROJECT_ID environment variable so the CLI can resolve the project
    without needing cwd-based detection.
    """
    project_id = _get_project_id(instance)

    env = {
        **os.environ,
        "SCULPT_PROJECT_ID": project_id,
    }

    full_args = args + ["--base-url", instance.backend_api_url, "--json"]
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main"] + full_args,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result.returncode, result.stdout


def _run_sculpt_raw(instance: SculptorInstance, args: list[str]) -> tuple[int, str]:
    """Like _run_sculpt but does not inject --json.

    Use for commands that produce non-standard output (e.g. NDJSON from --follow --json).
    """
    project_id = _get_project_id(instance)

    env = {
        **os.environ,
        "SCULPT_PROJECT_ID": project_id,
    }

    full_args = args + ["--base-url", instance.backend_api_url]
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main"] + full_args,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result.returncode, result.stdout


def _run_sculpt_capture(instance: SculptorInstance, args: list[str]) -> tuple[int, str, str]:
    """Like _run_sculpt_raw but also returns stderr.

    Use for error cases — cli_error writes the message to stderr (which the
    other helpers discard), so asserting on it needs the captured stream.
    """
    project_id = _get_project_id(instance)

    env = {
        **os.environ,
        "SCULPT_PROJECT_ID": project_id,
    }

    full_args = args + ["--base-url", instance.backend_api_url]
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main"] + full_args,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


class _Matcher:
    """Base class for flexible value matchers used in _assert_matches."""

    def matches(self, value: object) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class _AnyStr(_Matcher):
    """Matches any non-empty string."""

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and len(value) > 0

    def describe(self) -> str:
        return "<any non-empty str>"


class _AnyIsoDatetime(_Matcher):
    """Matches an ISO 8601 datetime string (e.g. '2026-01-15T10:30:00Z')."""

    def matches(self, value: object) -> bool:
        return isinstance(value, str) and len(value) >= 19 and "T" in value

    def describe(self) -> str:
        return "<any ISO datetime>"


class _AnyNumber(_Matcher):
    """Matches any int or float, optionally requiring >= 0."""

    def __init__(self, *, non_negative: bool = False) -> None:
        self._non_negative = non_negative

    def matches(self, value: object) -> bool:
        if not isinstance(value, (int, float)):
            return False
        if self._non_negative and value < 0:
            return False
        return True

    def describe(self) -> str:
        return "<any number >= 0>" if self._non_negative else "<any number>"


class _AnyIntOrNone(_Matcher):
    """Matches an int or None."""

    def matches(self, value: object) -> bool:
        return value is None or isinstance(value, int)

    def describe(self) -> str:
        return "<int | None>"


class _AnyStrOrNone(_Matcher):
    """Matches a string or None."""

    def matches(self, value: object) -> bool:
        return value is None or isinstance(value, str)

    def describe(self) -> str:
        return "<str | None>"


# Singleton matcher instances for use in expected dicts
ANY_STR = _AnyStr()
ANY_ISO_DATETIME = _AnyIsoDatetime()
ANY_NON_NEGATIVE_NUMBER = _AnyNumber(non_negative=True)
ANY_INT_OR_NONE = _AnyIntOrNone()
ANY_STR_OR_NONE = _AnyStrOrNone()


def _values_match(expected: object, actual: object) -> bool:
    """Recursively check whether actual matches the expected template."""
    if isinstance(expected, _Matcher):
        return expected.matches(actual)
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        if set(expected.keys()) != set(actual.keys()):
            return False
        return all(_values_match(expected[k], actual[k]) for k in expected)
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if len(expected) != len(actual):
            return False
        return all(_values_match(e, a) for e, a in zip(expected, actual))
    return expected == actual


def _describe_expected(value: object) -> object:
    """Convert matchers to their descriptions for error messages."""
    if isinstance(value, _Matcher):
        return value.describe()
    if isinstance(value, dict):
        return {k: _describe_expected(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_describe_expected(v) for v in value]
    return value


def _assert_matches(actual: object, expected: object) -> None:
    """Assert that actual matches the expected template.

    The expected template can contain:
    - Literal values (compared with ==)
    - _Matcher instances (e.g. ANY_STR, ANY_ISO_DATETIME)
    - Nested dicts/lists (recursively matched, keys must match exactly)
    """
    if not _values_match(expected, actual):
        expected_desc = _describe_expected(expected)
        exp_json = json.dumps(expected_desc, indent=2, default=str)
        act_json = json.dumps(actual, indent=2, default=str)
        raise AssertionError(f"Value mismatch:\n  expected: {exp_json}\n  actual:   {act_json}")


def _assert_is_iso_datetime(value: object) -> None:
    """Assert that a value is a string that looks like an ISO 8601 datetime."""
    assert isinstance(value, str), f"Expected str, got {type(value)}"
    assert len(value) >= 19, f"ISO datetime too short: {value!r}"
    assert "T" in value, f"Missing 'T' separator in ISO datetime: {value!r}"


def _assert_subset(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    """Assert that all key-value pairs in expected are present in actual.

    Produces a clear diff on failure showing only mismatched entries.
    """
    mismatches = {}
    for key, expected_val in expected.items():
        if key not in actual:
            mismatches[key] = {"expected": expected_val, "actual": "<missing>"}
        elif actual[key] != expected_val:
            mismatches[key] = {"expected": expected_val, "actual": actual[key]}
    assert not mismatches, f"Subset mismatch:\n{json.dumps(mismatches, indent=2, default=str)}"


# -- Expected key sets for each command's JSON output --------------------------

WORKSPACE_CREATE_KEYS = {"id", "repo_id", "description", "strategy", "source_branch"}

WORKSPACE_LIST_ALL_KEYS = {
    "id",
    "repo_id",
    "repo_path",
    "description",
    "strategy",
    "source_branch",
    "agent_count",
    "is_open",
    "created_at",
    "last_activity_at",
}

REPO_KEYS = {"id", "name", "path", "accessible", "created_at"}

AGENT_CREATE_KEYS = {"id", "title", "status", "model", "workspace_id", "created_at"}

AGENT_LIST_KEYS = {"id", "title", "status", "model", "workspace_id", "created_at"}

AGENT_SHOW_KEYS = {
    "id",
    "title",
    "status",
    "model",
    "interface",
    "created_at",
    "updated_at",
    "repo_id",
    "workspace_id",
    "is_deleted",
    "artifact_names",
    "current_activity",
    "last_activity",
    "task_completed",
    "task_total",
    "current_task_subject",
    "waiting_detail",
    "error_detail",
}

AGENT_STATUS_KEYS = {
    "id",
    "status",
    "updated_at",
    "current_activity",
    "last_activity",
    "waiting_detail",
    "error_detail",
    "task_completed",
    "task_total",
    "current_task_subject",
}

RUN_KEYS = {"workspace_id", "agent_id", "strategy", "model", "prompt"}


# ---------------------------------------------------------------------------
# Workspace tests: CLI → verify via CLI
# ---------------------------------------------------------------------------


@user_story("to create a workspace via the CLI and confirm it exists")
def test_workspace_create_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace with the sculpt CLI and verify it appears in the workspace list."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "CLI Created", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"
    created = json.loads(output)

    assert set(created.keys()) == WORKSPACE_CREATE_KEYS
    _assert_subset(
        {"description": "CLI Created", "strategy": "CLONE", "source_branch": None},
        created,
    )

    # List workspaces via CLI and verify the new workspace appears
    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "list", "--all"])
    assert exit_code == 0, f"workspace list failed: {output}"
    workspaces = json.loads(output)
    assert isinstance(workspaces, list)
    assert len(workspaces) >= 1

    ws_match = next(w for w in workspaces if w["id"] == created["id"])
    assert set(ws_match.keys()) == WORKSPACE_LIST_ALL_KEYS
    _assert_subset(
        {"description": "CLI Created", "strategy": "CLONE", "agent_count": 0},
        ws_match,
    )
    _assert_is_iso_datetime(ws_match["created_at"])
    _assert_is_iso_datetime(ws_match["last_activity_at"])


@user_story("to inspect workspace details via the CLI")
def test_workspace_show_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace and then retrieve its details via `sculpt workspace show`."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Show Test", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"
    created = json.loads(output)
    ws_id = created["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "show", ws_id])
    assert exit_code == 0, f"workspace show failed: {output}"
    detail = json.loads(output)

    assert set(detail.keys()) == WORKSPACE_LIST_ALL_KEYS
    _assert_subset(
        {
            "id": ws_id,
            "repo_id": created["repo_id"],
            "description": "Show Test",
            "strategy": "CLONE",
            "agent_count": 0,
        },
        detail,
    )
    _assert_is_iso_datetime(detail["created_at"])
    _assert_is_iso_datetime(detail["last_activity_at"])


@user_story("to delete a workspace via the CLI")
def test_workspace_delete_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace, delete it via CLI, and verify it no longer appears in the list."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Delete Me", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"
    created = json.loads(output)
    ws_id = created["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "delete", ws_id, "--yes"])
    assert exit_code == 0, f"workspace delete failed: {output}"
    deleted = json.loads(output)
    assert deleted == {"deleted": True, "id": ws_id}

    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "list", "--all"])
    assert exit_code == 0
    workspaces = json.loads(output)
    ws_ids = [w["id"] for w in workspaces]
    assert ws_id not in ws_ids


_WORKTREE_CREATE_TIMEOUT_S = 90.0


def _worktree_paths(user_repo_path: Path) -> list[Path]:
    """Return all worktree paths (except the main one) for the user's repo."""
    result = subprocess.run(
        ["git", "-C", str(user_repo_path), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    main_path = user_repo_path.resolve()
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            p = Path(line.removeprefix("worktree ").strip()).resolve()
            if p != main_path:
                paths.append(p)
    return paths


def _worktree_branch(worktree_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _wait_for_new_worktree(
    instance: SculptorInstance,
    before: set[Path],
    timeout_s: float = _WORKTREE_CREATE_TIMEOUT_S,
) -> Path:
    """Poll the user's repo until a new worktree (not in ``before``) appears, then return its path.

    Uses ``page.wait_for_timeout`` instead of ``time.sleep`` so the wait yields to the
    Playwright event loop and matches the project's integration-test idiom.
    """
    deadline = time.monotonic() + timeout_s
    user_repo_path = instance.project_path
    while time.monotonic() < deadline:
        new_paths = set(_worktree_paths(user_repo_path)) - before
        if new_paths:
            return next(iter(new_paths))
        instance.page.wait_for_timeout(500)
    final_paths = set(_worktree_paths(user_repo_path))
    raise AssertionError(f"no new worktree appeared within {timeout_s:.0f}s; git worktree list: {final_paths!r}")


@user_story(
    "to invoke `sculpt run --repo <already-registered path>` without seeing the SCU-1309"
    + " 'Failed to initialize repo (no response)' error"
)
def test_run_with_repo_to_already_registered_path_is_idempotent(
    sculptor_instance_: SculptorInstance,
) -> None:
    """SCU-1309 e2e: when --repo points at a path the backend already has registered
    (the common case for any agent running inside a Sculptor worktree), the CLI used
    to print 'Failed to initialize repo (no response)' and exit 1. With the fix it
    must look up the existing project on the 409 'already added' response and reuse
    its id, so creating a workspace+agent succeeds.

    This test drives the real sculpt subprocess against a real backend, exercising
    the full CLI -> /api/v1/projects/initialize -> /api/v1/projects -> /api/v1/workspaces
    chain. Without the fix, `sculpt run --repo <auto-registered project>` is the exact
    invocation pattern that blocks every agent that tries to spawn a workspace."""
    exit_code, output = _run_sculpt(
        sculptor_instance_,
        [
            "run",
            "scu-1309 idempotent --repo",
            "--repo",
            str(sculptor_instance_.project_path),
            "--model",
            "haiku",
            "--name",
            "SCU-1309 idempotent repo",
            "--strategy",
            "clone",
        ],
    )
    assert exit_code == 0, f"`sculpt run --repo <already-registered>` failed: {output}"
    assert "Failed to initialize repo (no response)" not in output
    result = json.loads(output)
    assert set(result.keys()) == RUN_KEYS
    _assert_subset({"strategy": "CLONE", "prompt": "scu-1309 idempotent --repo"}, result)


@user_story("to spawn a worktree-strategy agent via the sculpt CLI with an explicit branch name")
def test_run_creates_worktree_workspace_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """`sculpt run --strategy worktree --branch <base> --branch-name <new>` should create a real
    git worktree on disk on the requested new branch and a workspace whose strategy is WORKTREE."""
    base_branch = _worktree_branch(sculptor_instance_.project_path)
    new_branch = "dev/cli-worktree-explicit"

    before = set(_worktree_paths(sculptor_instance_.project_path))

    exit_code, output = _run_sculpt(
        sculptor_instance_,
        [
            "run",
            "Do something",
            "--model",
            "haiku",
            "--strategy",
            "worktree",
            "--branch",
            base_branch,
            "--branch-name",
            new_branch,
            "--name",
            "CLI Worktree Explicit",
        ],
    )
    assert exit_code == 0, f"run failed: {output}"
    result = json.loads(output)
    _assert_subset({"strategy": "WORKTREE"}, result)

    # Verify the workspace's recorded strategy/branch via `sculpt workspace show`.
    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "show", result["workspace_id"]])
    assert exit_code == 0, f"workspace show failed: {output}"
    ws_detail = json.loads(output)
    _assert_subset(
        {"description": "CLI Worktree Explicit", "strategy": "WORKTREE", "source_branch": base_branch},
        ws_detail,
    )

    worktree_path = _wait_for_new_worktree(sculptor_instance_, before)
    assert worktree_path.exists(), f"worktree path does not exist: {worktree_path}"
    assert _worktree_branch(worktree_path) == new_branch


@user_story("to spawn a worktree-strategy agent via the sculpt CLI without naming the new branch")
def test_run_creates_worktree_workspace_autogen_branch_name(sculptor_instance_: SculptorInstance) -> None:
    """When `--branch-name` is omitted, the CLI mirrors the UI by calling preview-branch-name to
    auto-fill a slug derived from the workspace name."""
    base_branch = _worktree_branch(sculptor_instance_.project_path)

    before = set(_worktree_paths(sculptor_instance_.project_path))

    exit_code, output = _run_sculpt(
        sculptor_instance_,
        [
            "run",
            "Do something",
            "--model",
            "haiku",
            "--strategy",
            "worktree",
            "--branch",
            base_branch,
            "--name",
            "CLI Worktree Autogen",
        ],
    )
    assert exit_code == 0, f"run failed: {output}"
    result = json.loads(output)
    _assert_subset({"strategy": "WORKTREE"}, result)

    worktree_path = _wait_for_new_worktree(sculptor_instance_, before)
    branch_on_worktree = _worktree_branch(worktree_path)
    # The auto-generated slug ends with the slugified workspace name; the full pattern depends
    # on a configurable `<user>/<slug>` prefix, so we only pin the trailing slug.
    assert branch_on_worktree.endswith("cli-worktree-autogen"), (
        f"expected auto-generated branch to end with 'cli-worktree-autogen', got: {branch_on_worktree!r}"
    )


@user_story("to list repos known to the server via the CLI")
def test_repo_list_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """The running test backend should have at least one repo registered."""
    exit_code, output = _run_sculpt(sculptor_instance_, ["repo", "list"])
    assert exit_code == 0, f"repo list failed: {output}"
    repos = json.loads(output)
    assert isinstance(repos, list)
    assert len(repos) >= 1

    repo = repos[0]
    assert set(repo.keys()) == REPO_KEYS
    assert isinstance(repo["id"], str)
    assert isinstance(repo["name"], str)
    assert isinstance(repo["path"], str)
    assert isinstance(repo["accessible"], bool)


@user_story("to show details of a specific repo via the CLI")
def test_repo_show_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Fetch the repo list, then show details for the first repo."""
    exit_code, output = _run_sculpt(sculptor_instance_, ["repo", "list"])
    assert exit_code == 0
    repos = json.loads(output)
    first_repo = repos[0]

    exit_code, output = _run_sculpt(sculptor_instance_, ["repo", "show", first_repo["id"]])
    assert exit_code == 0, f"repo show failed: {output}"
    detail = json.loads(output)

    assert set(detail.keys()) == REPO_KEYS
    _assert_subset(
        {
            "id": first_repo["id"],
            "name": first_repo["name"],
            "path": first_repo["path"],
            "accessible": first_repo["accessible"],
        },
        detail,
    )


# ---------------------------------------------------------------------------
# Workspace tests: CLI ↔ UI cross-channel
# ---------------------------------------------------------------------------


@user_story("to create a workspace via the CLI and see it in the UI")
def test_workspace_created_via_cli_visible_in_ui(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace via the sculpt CLI and verify it appears on the home page."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "CLI Visible In UI", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"

    page = sculptor_instance_.page
    navigate_to_home_page(page)

    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="CLI Visible In UI")
    expect(workspace_row).to_be_visible()


@user_story("to create a workspace in the UI and list it via the CLI")
def test_workspace_created_in_ui_visible_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace through the UI and verify it appears in `sculpt workspace list`."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello from UI",
        workspace_name="UI Created Workspace",
    )

    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "list", "--all"])
    assert exit_code == 0, f"workspace list failed: {output}"
    workspaces = json.loads(output)

    ws_match = next(w for w in workspaces if w.get("description") == "UI Created Workspace")
    _assert_subset({"strategy": "WORKTREE"}, ws_match)
    assert ws_match["agent_count"] >= 1


@user_story("to delete a workspace via the CLI and see it disappear from the UI")
def test_workspace_deleted_via_cli_disappears_from_ui(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace in the UI, delete it via CLI, and verify it's gone from the home page."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Doomed workspace",
        workspace_name="Will Be Deleted",
    )

    # Verify it's on the home page
    navigate_to_home_page(page)
    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="Will Be Deleted")
    expect(workspace_row).to_be_visible()

    # Find its ID via the CLI
    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "list", "--all"])
    assert exit_code == 0
    workspaces = json.loads(output)
    ws = next(w for w in workspaces if w.get("description") == "Will Be Deleted")

    # Delete via CLI
    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "delete", ws["id"], "--yes"])
    assert exit_code == 0
    deleted = json.loads(output)
    assert deleted == {"deleted": True, "id": ws["id"]}

    # The delete empties the workspace list while the page is parked on Home,
    # which re-offers the first-run new-workspace dialog. Wait it out and
    # dismiss it so the Home surface below is clickable and assertable.
    settle_first_run_offer(page)

    # Verify gone from UI
    navigate_to_home_page(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="Will Be Deleted")
    expect(workspace_row).not_to_be_visible()


# ---------------------------------------------------------------------------
# Agent tests: CLI → verify via CLI
# ---------------------------------------------------------------------------


@user_story("to create an agent via the CLI and see it in the agent list")
def test_agent_create_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace and agent via the CLI, then list agents in that workspace."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Agent Test WS", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"
    ws_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws_id])
    assert exit_code == 0, f"agent create failed: {output}"
    agent = json.loads(output)

    assert set(agent.keys()) == AGENT_CREATE_KEYS
    _assert_subset({"workspace_id": ws_id}, agent)
    _assert_is_iso_datetime(agent["created_at"])

    # List agents in the workspace
    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "list", "--workspace", ws_id])
    assert exit_code == 0, f"agent list failed: {output}"
    agents = json.loads(output)
    assert isinstance(agents, list)
    assert len(agents) >= 1

    agent_match = next(a for a in agents if a["id"] == agent["id"])
    assert set(agent_match.keys()) == AGENT_LIST_KEYS
    _assert_subset({"workspace_id": ws_id}, agent_match)
    _assert_is_iso_datetime(agent_match["created_at"])


@user_story("to inspect agent details via the CLI")
def test_agent_show_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create an agent and retrieve its details via `sculpt agent show`."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Agent Show WS", "--strategy", "clone"]
    )
    assert exit_code == 0
    ws = json.loads(output)

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws["id"]])
    assert exit_code == 0
    agent_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "show", agent_id])
    assert exit_code == 0, f"agent show failed: {output}"
    detail = json.loads(output)

    assert set(detail.keys()) == AGENT_SHOW_KEYS
    _assert_subset(
        {
            "id": agent_id,
            "workspace_id": ws["id"],
            "repo_id": ws["repo_id"],
            "interface": "API",
            "is_deleted": False,
        },
        detail,
    )
    assert isinstance(detail["artifact_names"], list)
    assert detail["task_completed"] >= 0
    assert detail["task_total"] >= 0
    _assert_is_iso_datetime(detail["created_at"])
    _assert_is_iso_datetime(detail["updated_at"])


@user_story("to check an agent's status via the CLI")
def test_agent_status_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create an agent and check its status via `sculpt agent status`."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Agent Status WS", "--strategy", "clone"]
    )
    assert exit_code == 0
    ws_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws_id])
    assert exit_code == 0
    agent_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "status", agent_id])
    assert exit_code == 0, f"agent status failed: {output}"
    status = json.loads(output)

    assert set(status.keys()) == AGENT_STATUS_KEYS
    _assert_subset({"id": agent_id}, status)
    assert isinstance(status["status"], str)
    assert status["task_completed"] >= 0
    assert status["task_total"] >= 0
    _assert_is_iso_datetime(status["updated_at"])


@user_story("to delete an agent via the CLI")
def test_agent_delete_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create an agent, delete it, and verify it no longer appears in the list."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Agent Delete WS", "--strategy", "clone"]
    )
    assert exit_code == 0
    ws_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws_id])
    assert exit_code == 0
    agent_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "delete", agent_id, "--workspace", ws_id])
    assert exit_code == 0, f"agent delete failed: {output}"
    deleted = json.loads(output)
    assert deleted == {"deleted": True, "id": agent_id}

    # If the agent was still running, the delete sets is_deleting for
    # cooperative shutdown — the agent may linger until the runner stops.
    # Poll until the agent disappears from the list.
    page = sculptor_instance_.page
    for _ in range(20):
        exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "list", "--workspace", ws_id])
        assert exit_code == 0
        agents = json.loads(output)
        agent_ids = [a["id"] for a in agents]
        if agent_id not in agent_ids:
            break
        page.wait_for_timeout(500)
    else:
        assert agent_id not in agent_ids, f"Agent {agent_id} still in list after 10s"


# ---------------------------------------------------------------------------
# Agent tests: CLI ↔ UI cross-channel
# ---------------------------------------------------------------------------


@user_story("to create an agent in the UI and list it via the CLI")
def test_agent_created_in_ui_visible_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace and agent through the UI, then list agents via the CLI."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Hello from UI agent",
        workspace_name="UI Agent Workspace",
    )

    # List all workspaces via CLI to find the one we just created
    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "list", "--all"])
    assert exit_code == 0
    workspaces = json.loads(output)
    ws = next(w for w in workspaces if w.get("description") == "UI Agent Workspace")

    # List agents in that workspace
    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "list", "--workspace", ws["id"]])
    assert exit_code == 0, f"agent list failed: {output}"
    agents = json.loads(output)
    assert len(agents) >= 1

    agent = agents[0]
    assert set(agent.keys()) == AGENT_LIST_KEYS
    _assert_subset({"workspace_id": ws["id"]}, agent)
    _assert_is_iso_datetime(agent["created_at"])


@user_story("to create a workspace and agent via CLI and see the agent in the UI")
def test_agent_created_via_cli_visible_in_ui(sculptor_instance_: SculptorInstance) -> None:
    """Create a workspace and agent via the CLI, then verify the workspace tab appears in the UI."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "CLI Agent UI Check", "--strategy", "clone"]
    )
    assert exit_code == 0
    ws_id = json.loads(output)["id"]

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws_id])
    assert exit_code == 0

    # The workspace should appear on the home page
    page = sculptor_instance_.page
    navigate_to_home_page(page)

    home_page = PlaywrightHomePage(page)
    workspace_row = home_page.get_workspace_rows().filter(has_text="CLI Agent UI Check")
    expect(workspace_row).to_be_visible()


@user_story("to create multiple workspaces via CLI and list them all")
def test_multiple_workspaces_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create several workspaces via the CLI and verify they all appear in the list."""
    names = ["Multi WS Alpha", "Multi WS Beta", "Multi WS Gamma"]
    created_ids = []

    for name in names:
        exit_code, output = _run_sculpt(
            sculptor_instance_, ["workspace", "create", "--name", name, "--strategy", "clone"]
        )
        assert exit_code == 0, f"workspace create failed for {name}: {output}"
        created = json.loads(output)
        _assert_subset({"description": name, "strategy": "CLONE"}, created)
        created_ids.append(created["id"])

    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "list", "--all"])
    assert exit_code == 0
    workspaces = json.loads(output)
    listed_ids = [w["id"] for w in workspaces]

    for ws_id in created_ids:
        assert ws_id in listed_ids


@user_story("to use the `sculpt run` shortcut to create a workspace and agent in one step")
def test_run_command_creates_workspace_and_agent(sculptor_instance_: SculptorInstance) -> None:
    """The `sculpt run` command should create a workspace with an agent in a single step."""
    exit_code, output = _run_sculpt(
        sculptor_instance_,
        ["run", "--model", "haiku", "--name", "Run Command Test", "--strategy", "clone", "Do something"],
    )
    assert exit_code == 0, f"run command failed: {output}"
    result = json.loads(output)

    assert set(result.keys()) == RUN_KEYS
    _assert_subset(
        {"strategy": "CLONE", "model": "CLAUDE-4-HAIKU", "prompt": "Do something"},
        result,
    )

    # Verify the workspace exists and has the right description
    ws_id = result["workspace_id"]
    exit_code, output = _run_sculpt(sculptor_instance_, ["workspace", "show", ws_id])
    assert exit_code == 0
    ws_detail = json.loads(output)
    _assert_subset({"description": "Run Command Test", "strategy": "CLONE"}, ws_detail)

    # Verify the agent exists in that workspace
    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "list", "--workspace", ws_id])
    assert exit_code == 0
    agents = json.loads(output)
    agent_match = next(a for a in agents if a["id"] == result["agent_id"])
    _assert_subset({"model": "CLAUDE-4-HAIKU"}, agent_match)


# ---------------------------------------------------------------------------
# Harness selection / most-recently-used (MRU) harness tests
#
# The CLI's JSON output has no explicit harness field, but the auto-assigned
# agent title encodes the type ("Claude N" / "Terminal N" / "Pi N"), so these
# tests verify the harness via the title. Terminal is used as the non-default
# harness: it has no enable gate and creates a waiting agent whose title is
# stable (no prompt, so no later prompt-derived rename).
# ---------------------------------------------------------------------------


@user_story("to create agents with --harness and have a bare create reuse the most-recently-used one")
def test_agent_create_harness_records_and_reuses_mru_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """`sculpt agent create --harness X` records X as the default; a later bare create reuses it."""
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Harness MRU WS", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"
    ws_id = json.loads(output)["id"]

    # With no --harness and no prior choice, the server defaults to Claude.
    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws_id])
    assert exit_code == 0, f"agent create failed: {output}"
    assert json.loads(output)["title"].startswith("Claude"), output

    # An explicit --harness creates that type and records it as the new default.
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["agent", "create", "--workspace", ws_id, "--harness", "Terminal"]
    )
    assert exit_code == 0, f"agent create --harness Terminal failed: {output}"
    assert json.loads(output)["title"].startswith("Terminal"), output

    # A subsequent bare create reuses the recorded harness (Terminal), not Claude.
    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "create", "--workspace", ws_id])
    assert exit_code == 0, f"agent create failed: {output}"
    assert json.loads(output)["title"].startswith("Terminal"), output


@user_story("to be told that `sculpt run` cannot create a terminal agent, since it always sends a prompt")
def test_run_rejects_explicit_terminal_harness_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """`sculpt run --harness Terminal` is rejected up front (a terminal agent can't take a prompt)."""
    exit_code, _stdout, stderr = _run_sculpt_capture(
        sculptor_instance_, ["run", "do something", "--strategy", "clone", "--harness", "Terminal"]
    )
    assert exit_code == 1, f"expected rejection, got exit {exit_code}; stderr={stderr!r}"
    assert "sculpt run" in stderr, stderr


@user_story("to pass an explicit chat harness to `sculpt run`")
def test_run_accepts_explicit_chat_harness_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """`sculpt run --harness Claude` is accepted and creates the workspace + a chat agent."""
    exit_code, output = _run_sculpt(
        sculptor_instance_,
        ["run", "do something", "--strategy", "clone", "--model", "haiku", "--harness", "Claude"],
    )
    assert exit_code == 0, f"run --harness Claude failed: {output}"
    result = json.loads(output)
    assert set(result.keys()) == RUN_KEYS

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "show", result["agent_id"]])
    assert exit_code == 0, f"agent show failed: {output}"
    assert not json.loads(output)["title"].startswith("Terminal"), output


@user_story("to have `sculpt run` reuse the most-recently-used harness, falling back to Claude for a terminal default")
def test_run_reuses_mru_and_falls_back_for_terminal_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """A bare `sculpt run` reads the shared default; a Terminal default falls back to Claude (it has a prompt)."""
    # Record a Terminal default through `agent create` (shares the server-side MRU with run).
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["workspace", "create", "--name", "Run MRU WS", "--strategy", "clone"]
    )
    assert exit_code == 0, f"workspace create failed: {output}"
    ws_id = json.loads(output)["id"]
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["agent", "create", "--workspace", ws_id, "--harness", "Terminal"]
    )
    assert exit_code == 0, f"agent create --harness Terminal failed: {output}"
    assert json.loads(output)["title"].startswith("Terminal"), output

    # A bare `run` always sends a prompt, so the Terminal default must fall back to a chat
    # agent rather than failing — the run succeeds and the created agent is not a terminal one.
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["run", "do something", "--strategy", "clone", "--model", "haiku"]
    )
    assert exit_code == 0, f"run with a Terminal MRU should fall back to Claude, not fail: {output}"
    result = json.loads(output)
    assert set(result.keys()) == RUN_KEYS

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "show", result["agent_id"]])
    assert exit_code == 0, f"agent show failed: {output}"
    assert not json.loads(output)["title"].startswith("Terminal"), output


# ---------------------------------------------------------------------------
# Agent tests: WebSocket-powered commands
# ---------------------------------------------------------------------------


def _create_fake_claude_agent(
    instance: SculptorInstance,
    workspace_name: str,
    prompt: str,
) -> tuple[str, str]:
    """Create a FakeClaude agent via the UI and return (workspace_id, agent_id).

    Uses start_task_and_wait_for_ready to create the agent with FakeClaude,
    then resolves the IDs via the CLI.
    """
    page = instance.page
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=prompt,
        workspace_name=workspace_name,
    )

    exit_code, output = _run_sculpt(instance, ["workspace", "list", "--all"])
    assert exit_code == 0, f"workspace list failed: {output}"
    workspaces = json.loads(output)
    ws = next(w for w in workspaces if w.get("description") == workspace_name)

    exit_code, output = _run_sculpt(instance, ["agent", "list", "--workspace", ws["id"]])
    assert exit_code == 0, f"agent list failed: {output}"
    agents = json.loads(output)
    assert len(agents) >= 1

    return ws["id"], agents[0]["id"]


def _parse_ndjson(output: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON output into a list of event dicts."""
    lines = [line for line in output.strip().split("\n") if line]
    return [json.loads(line) for line in lines]


def _expected_user_message(prompt_text: str, *, sent_via: str | None = None) -> dict[str, Any]:
    """Build the expected template for a FakeClaude user message.

    Args:
        prompt_text: The text content of the message.
        sent_via: Expected value of the sentVia field. None for UI-sent messages,
            "sculpt" for messages sent via the sculpt CLI.
    """
    return {
        "role": "USER",
        "id": ANY_STR,
        "content": [{"objectType": "TextBlock", "type": "text", "text": prompt_text}],
        "parentToolUseId": None,
        "approximateCreationTime": ANY_ISO_DATETIME,
        "turnMetrics": None,
        "stopped": False,
        "sentVia": sent_via,
    }


def _expected_assistant_message(response_text: str) -> dict[str, Any]:
    """Build the expected template for a FakeClaude assistant message."""
    return {
        "role": "ASSISTANT",
        "id": ANY_STR,
        "content": [{"objectType": "TextBlock", "type": "text", "text": response_text}],
        "parentToolUseId": None,
        "approximateCreationTime": ANY_ISO_DATETIME,
        "turnMetrics": {
            "durationSeconds": ANY_NON_NEGATIVE_NUMBER,
            "inputTokens": ANY_INT_OR_NONE,
            "outputTokens": ANY_INT_OR_NONE,
            "reasoningTokens": ANY_INT_OR_NONE,
            "changedFiles": [],
            "contextTotalTokens": ANY_INT_OR_NONE,
            "autoCompactThreshold": ANY_INT_OR_NONE,
        },
        "stopped": False,
        "sentVia": None,
    }


def _expected_status_event(agent_id: str) -> dict[str, Any]:
    """Build the expected template for a --follow status NDJSON event."""
    return {
        "type": "status",
        "data": {
            "id": agent_id,
            "status": "READY",
            "updated_at": ANY_ISO_DATETIME,
            "current_activity": ANY_STR_OR_NONE,
            "last_activity": ANY_STR_OR_NONE,
            "waiting_detail": None,
            "error_detail": None,
            "task_completed": 0,
            "task_total": 0,
            "current_task_subject": None,
        },
    }


@user_story("to view agent messages via the CLI")
def test_agent_messages_via_cli(sculptor_instance_: SculptorInstance) -> None:
    """Create an agent with a prompt and check its messages via `sculpt agent messages`."""
    prompt = 'fake_claude:text `{"text": "Hello from FakeClaude"}`'
    _ws_id, agent_id = _create_fake_claude_agent(
        sculptor_instance_,
        workspace_name="Agent Messages WS",
        prompt=prompt,
    )

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "messages", agent_id])
    assert exit_code == 0, f"agent messages failed: {output}"
    messages = json.loads(output)
    assert isinstance(messages, list)
    assert len(messages) == 2, f"Expected exactly 2 messages (user + assistant), got {len(messages)}"

    _assert_matches(messages[0], _expected_user_message(prompt))
    _assert_matches(messages[1], _expected_assistant_message("Hello from FakeClaude"))


@user_story("to view rich agent details via the CLI show command")
def test_agent_show_includes_rich_fields(sculptor_instance_: SculptorInstance) -> None:
    """Verify `sculpt agent show` returns rich WebSocket-sourced fields for a completed agent."""
    ws_id, agent_id = _create_fake_claude_agent(
        sculptor_instance_,
        workspace_name="Agent Rich Show WS",
        prompt='fake_claude:text `{"text": "Show me details"}`',
    )

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "show", agent_id])
    assert exit_code == 0, f"agent show failed: {output}"
    detail = json.loads(output)

    assert set(detail.keys()) == AGENT_SHOW_KEYS
    _assert_subset(
        {
            "id": agent_id,
            "workspace_id": ws_id,
            "is_deleted": False,
            "interface": "API",
            "status": "READY",
            "error_detail": None,
        },
        detail,
    )
    _assert_is_iso_datetime(detail["created_at"])
    _assert_is_iso_datetime(detail["updated_at"])


@user_story("to follow agent status via the CLI and get NDJSON output")
def test_agent_status_follow_json(sculptor_instance_: SculptorInstance) -> None:
    """Create a completed FakeClaude agent and follow its status with --follow --json.

    A completed agent is in terminal state (READY), so --follow should emit
    one status event and one exit event, then exit with code 0.
    """
    _ws_id, agent_id = _create_fake_claude_agent(
        sculptor_instance_,
        workspace_name="Agent Follow WS",
        prompt='fake_claude:text `{"text": "Follow my status"}`',
    )

    exit_code, output = _run_sculpt_raw(sculptor_instance_, ["agent", "status", agent_id, "--follow", "--json"])
    assert exit_code == 0, f"agent status --follow failed with code {exit_code}: {output}"

    events = _parse_ndjson(output)
    assert len(events) == 2, f"Expected exactly 2 NDJSON lines (status + exit), got {len(events)}"

    _assert_matches(events[0], _expected_status_event(agent_id))
    assert events[1] == {"type": "exit", "data": {"reason": "terminal_state"}}


@user_story("to follow agent messages via the CLI and get NDJSON output")
def test_agent_messages_follow_json(sculptor_instance_: SculptorInstance) -> None:
    """Create a completed FakeClaude agent and follow its messages with --follow --json.

    Should emit a status event, message events (user + assistant), and an exit event.
    """
    prompt = 'fake_claude:text `{"text": "Follow my messages"}`'
    _ws_id, agent_id = _create_fake_claude_agent(
        sculptor_instance_,
        workspace_name="Agent Msg Follow WS",
        prompt=prompt,
    )

    exit_code, output = _run_sculpt_raw(sculptor_instance_, ["agent", "messages", agent_id, "--follow", "--json"])
    assert exit_code == 0, f"agent messages --follow failed with code {exit_code}: {output}"

    events = _parse_ndjson(output)
    assert len(events) == 4, f"Expected exactly 4 NDJSON lines (status + 2 messages + exit), got {len(events)}"

    _assert_matches(events[0], _expected_status_event(agent_id))
    _assert_matches(events[1], {"type": "message", "data": _expected_user_message(prompt)})
    _assert_matches(events[2], {"type": "message", "data": _expected_assistant_message("Follow my messages")})
    assert events[3] == {"type": "exit", "data": {"reason": "terminal_state"}}


@user_story("to see artifact names produced by a FakeClaude agent that uses TaskCreate")
def test_agent_show_artifact_names(sculptor_instance_: SculptorInstance) -> None:
    """Create a FakeClaude agent that uses TaskCreate, producing a PLAN artifact.

    Verify that `sculpt agent show` reports the artifact name in `artifact_names`.
    """
    prompt = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "First task", "status": "in_progress", "activeForm": "Working on first task"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Second task", "status": "pending", "activeForm": "Working on second task"}}
  ]
}`"""
    ws_id, agent_id = _create_fake_claude_agent(
        sculptor_instance_,
        workspace_name="Agent Artifact WS",
        prompt=prompt,
    )

    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "show", agent_id])
    assert exit_code == 0, f"agent show failed: {output}"
    detail = json.loads(output)

    assert set(detail.keys()) == AGENT_SHOW_KEYS
    _assert_subset(
        {
            "id": agent_id,
            "workspace_id": ws_id,
            "is_deleted": False,
            "interface": "API",
            "status": "READY",
            "error_detail": None,
        },
        detail,
    )
    assert sorted(detail["artifact_names"]) == ["PLAN"]


# ---------------------------------------------------------------------------
# sent_via badge tests: sculpt CLI → verify badge in UI
# ---------------------------------------------------------------------------


@user_story("to see which messages were sent by sculpt in the UI")
def test_sculpt_send_shows_sent_via_badge_in_ui(sculptor_instance_: SculptorInstance) -> None:
    """Send a follow-up message via sculpt CLI and verify the 'via sculpt' badge is shown in the UI.

    Also confirms that the initial UI-sent message does NOT display the badge.
    """
    prompt = 'fake_claude:text `{"text": "Initial response"}`'
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=prompt,
        workspace_name="Sculpt Badge WS",
        wait_for_agent_to_finish=True,
    )
    agent_id = task_page.get_task_id()
    ws_match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", sculptor_instance_.page.url)
    assert ws_match, f"Could not extract workspace ID from URL: {sculptor_instance_.page.url}"
    workspace_id = ws_match.group(1)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up message via sculpt CLI
    follow_up = 'fake_claude:text `{"text": "Sculpt follow-up"}`'
    exit_code, output = _run_sculpt(
        sculptor_instance_, ["agent", "send", agent_id, follow_up, "--workspace", workspace_id]
    )
    assert exit_code == 0, f"agent send failed: {output}"

    # Wait for the sculpt-sent message and the agent's response to appear
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The sculpt-sent message is the 3rd message (index 2, 0-based)
    messages = chat_panel.get_messages()
    sculpt_message = messages.nth(2)

    # Verify the 'via sculpt' badge is visible on the sculpt-sent message
    badge = chat_panel.get_sent_via_badge(sculpt_message)
    expect(badge).to_be_visible()
    expect(badge).to_contain_text("sculpt")

    # Verify the initial UI-sent message (index 0) has NO badge
    ui_message = messages.nth(0)
    ui_badge = chat_panel.get_sent_via_badge(ui_message)
    expect(ui_badge).to_have_count(0)

    # Also verify that the CLI messages output includes sentVia for the sculpt-sent message
    exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "messages", agent_id])
    assert exit_code == 0, f"agent messages failed: {output}"
    cli_messages = json.loads(output)
    assert len(cli_messages) == 4, f"Expected 4 messages, got {len(cli_messages)}"
    _assert_matches(cli_messages[2], _expected_user_message(follow_up, sent_via="sculpt"))
    _assert_matches(cli_messages[0], _expected_user_message(prompt, sent_via=None))


# ---------------------------------------------------------------------------
# sculpt agent send → registered terminal agent: prompt must be typed into the PTY
# ---------------------------------------------------------------------------

# A fake registered program: idle at its prompt, echo each received line as
# RECEIVED:<line>, then go busy. The IDLE-DONE marker is assembled via printf so
# the echoed command line never contains it (mirrors
# test_terminal_agent_automated_prompts), letting the test gate on the marker.
_FAKE_PROMPTS_COMMAND = (
    "echo FAKE-PROMPTS-BANNER; sculpt signal idle; printf %sDONE IDLE-; echo; "
    + "while read -r _line; do echo RECEIVED:$_line; sculpt signal busy; done"
)

_NEUTRAL_DOT = re.compile(r"^(read|unread)$")


@user_story("to send a prompt to a registered terminal agent with `sculpt agent send`")
def test_sculpt_agent_send_types_into_registered_terminal_agent_pty(
    sculptor_instance_: SculptorInstance,
) -> None:
    """`sculpt agent send` to a registered terminal agent must type the prompt
    into the agent's PTY (as the action buttons and CI Babysitter do), not queue
    it as a chat message the terminal agent never consumes.

    A fake registered program opts into automated prompts, signals idle, and
    echoes each stdin line as ``RECEIVED:<line>``. With it at its prompt, running
    ``sculpt agent send <agent> <msg>`` must surface ``RECEIVED:<msg>`` in the
    terminal buffer. With the bug present the CLI's message is queued as a
    ChatInputUserMessage and never reaches the PTY, so the echo never appears and
    this wait times out.
    """
    page = sculptor_instance_.page

    # A workspace with a chat agent gives us somewhere to launch the terminal
    # agent; the prompt content is irrelevant to this test.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "ready"}`',
        workspace_name="Sculpt Terminal Send WS",
    )
    ws_match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", page.url)
    assert ws_match, f"Could not extract workspace ID from URL: {page.url}"
    workspace_id = ws_match.group(1)
    chat_agent_id = task_page.get_task_id()

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-prompts.toml").write_text(
        f'display_name = "Fake Prompts"\nlaunch_command = "{_FAKE_PROMPTS_COMMAND}"\naccepts_automated_prompts = true\n'
    )
    try:
        # Launch the registered terminal agent via the section `+` add-panel
        # dropdown and wait until it is at its prompt.
        panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
        dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
        dropdown.open()
        dropdown.open_agent_type_submenu()
        registered_item = dropdown.get_agent_type_item_registered("fake-prompts")
        expect(registered_item).to_be_visible()
        registered_item.click()

        prompts_tab = panel_tabs.get_panel_tab_by_name("Fake Prompts 1").first
        expect(prompts_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        wait_for_xterm_substring(page, "FAKE-PROMPTS-BANNER")
        # The idle signal landed in the backend: the program is at its prompt.
        wait_for_xterm_substring(page, "IDLE-DONE")
        expect(prompts_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT)

        # Resolve the terminal agent's id from the CLI (it is the only agent in
        # the workspace that is not the original chat agent).
        exit_code, output = _run_sculpt(sculptor_instance_, ["agent", "list", "--workspace", workspace_id])
        assert exit_code == 0, f"agent list failed: {output}"
        other_agent_ids = [a["id"] for a in json.loads(output) if a["id"] != chat_agent_id]
        assert len(other_agent_ids) == 1, f"Expected exactly one terminal agent, got {other_agent_ids}"
        terminal_agent_id = other_agent_ids[0]

        # No spaces: the prompt lands on one xterm line and the echoed RECEIVED
        # line matches exactly (the program's `echo RECEIVED:$_line` is unquoted).
        prompt_text = "SCULPT-CLI-TERMINAL-PROMPT"
        exit_code, output = _run_sculpt(
            sculptor_instance_,
            ["agent", "send", terminal_agent_id, prompt_text, "--workspace", workspace_id],
        )
        assert exit_code == 0, f"agent send failed: {output}"

        # The prompt was typed into the PTY: the program echoes it back. (The
        # line-discipline echo of the typed text also appears, but only the
        # program's output carries the RECEIVED: prefix.)
        wait_for_xterm_substring(page, f"RECEIVED:{prompt_text}")
    finally:
        (registrations_dir / "fake-prompts.toml").unlink(missing_ok=True)
