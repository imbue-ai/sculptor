"""End-to-end tests for the workspace delete + cleanup teardown path.

Deleting a workspace runs a cascade with several moving parts (see
``web/app.py::delete_workspace`` and
``workspace_service/default_implementation.py::delete_workspace``):

1. Cascade-delete every agent/task in the workspace. A *running* task takes the
   cooperative ``is_deleting`` shutdown path (signal the runner, let it finalize
   on exit); an *idle* task is finalized immediately.
2. On a background thread after the soft-delete commits:
   ``stop_terminals_for_environment`` kills any live PTYs *first* (before the
   working directory is torn out from under them — SCU-1424), then
   ``remove_worktree`` removes the git worktree, then the environment directory
   is ``rmtree``'d.
3. The UI removes the workspace tab optimistically.

Other tests cover these pieces in isolation — ``test_worktree_deletion_policies``
removes a worktree with no terminal/agent activity, and
``test_terminal_close_kills_shell`` kills a shell by closing its *tab*, not by
deleting the workspace. Neither deletes a workspace that simultaneously has a
live PTY and an agent and asserts the whole teardown happens. These two tests
close that gap, one per task-finalization path (idle and running).
"""

import os
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from sculptor.testing.elements.terminal import get_xterm_buffer_text
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import run_command_in_active_terminal
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import request_with_retry
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _workspace_id_from_url(page: Page) -> str:
    """Extract the ``ws_...`` id from the current agent-page URL."""
    match = re.search(r"/ws/(ws_[a-z0-9]+)", page.url)
    assert match, f"could not extract workspace_id from URL: {page.url}"
    return match.group(1)


def _worktree_paths(user_repo_path: Path) -> list[Path]:
    """Return every git worktree path registered in the user repo except the main checkout."""
    result = subprocess.run(
        ["git", "-C", str(user_repo_path), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths: list[Path] = []
    main_path = user_repo_path.resolve()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            p = Path(line.removeprefix("worktree ").strip()).resolve()
            if p != main_path:
                paths.append(p)
    return paths


def _wait_for_worktree_removed(
    page: Page, user_repo_path: Path, worktree_path: Path, timeout_ms: int = 30_000
) -> None:
    """Poll ``git worktree list`` until ``worktree_path`` is gone, else fail.

    Worktree removal runs on the post-commit background teardown thread, so the
    DELETE request returns before it finishes — this waits for the side effect.
    """
    for _ in range(timeout_ms // 100):
        if worktree_path.resolve() not in _worktree_paths(user_repo_path):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"worktree {worktree_path} was not removed within {timeout_ms}ms")


def _read_shell_pid_from_active_terminal(page: Page) -> int:
    """Type ``echo "PID:$$"`` into the active xterm and return its shell pid.

    The typed command shows up as the literal ``PID:$$`` in the buffer (the
    shell expands ``$$`` only when it executes), so the regex ``PID:(\\d+)``
    matches only the output line. ``window.__xterm`` is the active terminal.
    """
    run_command_in_active_terminal(page, 'echo "PID:$$"')
    try:
        result = page.wait_for_function(
            """() => {
                const xterm = window.__xterm;
                if (!xterm) return null;
                const buffer = xterm.buffer.active;
                const lines = [];
                for (let i = 0; i <= buffer.baseY + buffer.cursorY; i++) {
                    const line = buffer.getLine(i);
                    if (line) lines.push(line.translateToString(true));
                }
                const match = /PID:(\\d+)/.exec(lines.join('\\n'));
                return match ? parseInt(match[1]) : null;
            }"""
        )
        return result.json_value()
    except PlaywrightTimeoutError:
        raise AssertionError(f"never saw PID marker; buffer was:\n{get_xterm_buffer_text(page)!r}")


def _wait_for_dead(page: Page, pid: int, timeout: float = 15.0) -> bool:
    """Return True once ``os.kill(pid, 0)`` raises ProcessLookupError.

    The frontend DELETE is fire-and-forget; the backend then has to cascade the
    task deletes, commit, and run the background teardown that stops the PTY
    (SIGHUP → SIGTERM → SIGKILL), so the deadline is wider than the tab-close path.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(100)


def _assert_workspace_gone_from_backend(page: Page, workspace_id: str) -> None:
    """Assert the workspace now 404s — proves the soft-delete (and cascade) committed."""
    base_url = page.url.split("#")[0].rstrip("/")
    response = request_with_retry(page.request.get, f"{base_url}/api/v1/workspaces/{workspace_id}")
    assert response.status == 404, f"expected workspace {workspace_id} to be gone, got {response.status}"


@user_story("to fully clean up an open terminal and idle agent when I delete the workspace")
def test_delete_workspace_with_open_terminal_kills_pty_and_removes_worktree(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting a workspace with a live terminal kills the PTY and removes the worktree.

    The agent is idle (Fake Claude's instant default response), so this exercises
    the idle-task finalization path alongside the PTY stop + worktree removal.
    """
    page = sculptor_instance_.page
    user_repo_path = sculptor_instance_.project_path

    worktrees_before = set(_worktree_paths(user_repo_path))
    start_task_and_wait_for_ready(page, prompt="Hello", workspace_name="Deletion Cleanup WS")
    workspace_id = _workspace_id_from_url(page)

    new_worktrees = set(_worktree_paths(user_repo_path)) - worktrees_before
    assert len(new_worktrees) == 1, f"expected exactly one new worktree, got {new_worktrees}"
    worktree_path = new_worktrees.pop()

    # Open the bottom terminal panel and capture its live shell pid.
    open_terminal_and_wait(page)
    shell_pid = _read_shell_pid_from_active_terminal(page)
    assert shell_pid > 0
    os.kill(shell_pid, 0)  # sanity: the shell is reachable on the host

    sidebar = get_workspace_sidebar(page)
    workspace_rows = sidebar.get_workspace_rows()
    expect(workspace_rows).to_have_count(1)

    sidebar.delete_workspace_via_context_menu(workspace_rows.first)

    # UI: the tab is removed (optimistically, before the backend confirms).
    expect(sidebar.get_delete_confirmation_dialog()).to_be_hidden()
    expect(workspace_rows).to_have_count(0)

    # Backend teardown: the PTY shell process is killed, not just disconnected.
    assert _wait_for_dead(page, shell_pid), (
        f"shell pid {shell_pid} still alive after workspace delete — the PTY was leaked"
    )

    # Backend teardown: the git worktree is removed.
    _wait_for_worktree_removed(page, user_repo_path, worktree_path)

    # The soft-delete (with its cascade task delete) committed.
    _assert_workspace_gone_from_backend(page, workspace_id)


@user_story("to cleanly delete a workspace whose agent is still running")
def test_delete_workspace_with_running_agent_finalizes_and_removes_worktree(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Deleting a workspace while its agent is mid-run tears everything down cleanly.

    A long ``fake_claude:sleep`` keeps the agent in a running (cancellable) state,
    so the cascade delete hits the cooperative ``is_deleting`` shutdown path for a
    *running* task — the complement of the idle path in the test above.
    """
    page = sculptor_instance_.page
    user_repo_path = sculptor_instance_.project_path

    worktrees_before = set(_worktree_paths(user_repo_path))
    # wait_for_agent_to_finish=False: we want the agent still running when we delete.
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:sleep `{"seconds": 120}`',
        workspace_name="Running Agent Delete WS",
        wait_for_agent_to_finish=False,
    )
    workspace_id = _workspace_id_from_url(page)

    new_worktrees = set(_worktree_paths(user_repo_path)) - worktrees_before
    assert len(new_worktrees) == 1, f"expected exactly one new worktree, got {new_worktrees}"
    worktree_path = new_worktrees.pop()

    # Confirm the agent is actually running (cancellable) before we delete.
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_stop_button()).to_be_visible(timeout=30_000)

    sidebar = get_workspace_sidebar(page)
    workspace_rows = sidebar.get_workspace_rows()
    expect(workspace_rows).to_have_count(1)

    sidebar.delete_workspace_via_context_menu(workspace_rows.first)

    # UI: the tab is removed even though the agent was running.
    expect(sidebar.get_delete_confirmation_dialog()).to_be_hidden()
    expect(workspace_rows).to_have_count(0)

    # Backend teardown completes despite the running agent: the worktree is
    # removed (which only happens after the soft-delete commits), and the
    # workspace 404s — proving the running task was finalized in the cascade.
    _wait_for_worktree_removed(page, user_repo_path, worktree_path)
    _assert_workspace_gone_from_backend(page, workspace_id)
