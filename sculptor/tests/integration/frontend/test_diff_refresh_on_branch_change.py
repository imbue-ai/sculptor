"""Integration test: diff refreshes when the current branch changes.

When the current branch changes, the file browser should update to reflect
the new branch's diff — just like it already does when the target branch
changes.
"""

import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.file_tree import get_changes_tree
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


def _get_workspace_working_dir(sculptor_instance: SculptorInstance) -> Path:
    """Find the clone workspace's working directory.

    After a workspace is created via the UI (clone mode), the clone lives at
    ``sculptor_folder / "workspaces" / env_id / "code"``.
    """
    workspaces_dir = sculptor_instance.sculptor_folder / "workspaces"
    code_dirs = sorted(workspaces_dir.glob("*/code"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert code_dirs, f"No workspace clone found under {workspaces_dir}"
    return code_dirs[0]


@user_story("to see the diff update when the current branch changes")
def test_diff_refreshes_when_current_branch_changes(sculptor_instance_: SculptorInstance) -> None:
    """The changes tree should update when the current branch changes.

    Steps:
    1. Agent writes hello.py — it appears in the Uncommitted changes tree.
    2. *Outside* the agent (directly on the filesystem), commit hello.py and
       check out a new branch at origin/main so the workspace has zero diff.
    3. The branch polling manager detects the branch change within 3 seconds
       and pushes a WebSocket update.  The frontend should detect this, clear
       stale diff data, and refetch — making hello.py disappear from Changes.

    By performing the checkout outside the agent, ``on_diff_needed()`` does
    NOT fire, so the only path that can update the diff is the frontend
    detecting the branch change via the ``workspaceBranchAtomFamily`` atom.
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace (clone mode — the test relies on `origin/main`
    # being available in the workspace's checkout, which only exists in
    # clones) and have the agent write a file.
    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT, mode="CLONE")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes panel and verify hello.py is listed.
    task_page.activate_changes_panel()
    changes_tree = get_changes_tree(page)
    expect(changes_tree).to_be_visible()
    hello_row = changes_tree.get_tree_rows().filter(has_text="hello.py")
    expect(hello_row).to_be_visible()

    # Wait for branch polling to publish its baseline before changing the
    # branch externally. The polling callback's diff-refresh path only fires
    # on a branch *transition* (`repo_polling_manager.py` — requires
    # `_last_branch is not None`); the first poll fires 3s after the poller
    # starts, so without this wait, a fast checkout can beat the first poll
    # and set the baseline to the new branch — bypassing the refresh.
    task_page.get_branch_name_element()

    # Step 2: Commit and checkout *outside* the agent — no on_diff_needed().
    workspace_dir = _get_workspace_working_dir(sculptor_instance_)
    subprocess.run(
        ["git", "add", "hello.py"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add hello"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "fresh-from-main", "origin/main"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    # Step 3: The changes tree should no longer show hello.py.
    # Allow up to 15 seconds for the branch polling (3s interval) to detect
    # the change and the frontend to clear + refetch the diff.
    expect(hello_row).to_be_hidden(timeout=15_000)
