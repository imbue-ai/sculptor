"""Integration tests: the workspace's git state updates live in the UI.

These cover the two signals the backend git-state scanner produces and pushes
over the websocket stream:

- the **current branch** shown in the workspace banner, and
- the **target branches** offered by the merge-target selector.

Both are driven by changing git state *outside* the agent (directly on the
filesystem), so the only thing that can update the UI is the scanner detecting
the change and emitting an update — exactly the path a refactor of the scanning
mechanism must preserve. They are the e2e backstop for that refactor.

The scanner runs on a ~3s interval; the assertions rely on Playwright's default
timeout (not a lowered one), which comfortably covers several scan cycles.
"""

import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
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


@user_story("to see the current branch update in the banner after an external checkout")
def test_current_branch_updates_after_external_checkout(sculptor_instance_: SculptorInstance) -> None:
    """An external ``git checkout`` of a new branch should surface in the banner.

    The scanner detects the moved ``HEAD`` and pushes a ``WorkspaceBranchInfo``;
    the banner's branch name should change to the new branch within a few poll
    cycles. Performing the checkout outside the agent guarantees nothing else
    updates the branch name.
    """
    page = sculptor_instance_.page

    # Clone mode so `origin/main` exists in the workspace checkout to branch from.
    task_page = start_task_and_wait_for_ready(
        page, prompt=_WRITE_FILE_PROMPT, mode="CLONE", backend_url=sculptor_instance_.backend_api_url
    )
    wait_for_completed_message_count(chat_panel=task_page.get_chat_panel(), expected_message_count=2)

    # Wait for the scanner to publish the baseline branch before changing it.
    branch_name_element = task_page.get_branch_name_element()
    expect(branch_name_element).not_to_have_text("branch-from-outside")

    workspace_dir = _get_workspace_working_dir(sculptor_instance_)
    subprocess.run(
        ["git", "checkout", "-b", "branch-from-outside", "origin/main"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    expect(branch_name_element).to_have_text("branch-from-outside")


@user_story("to see a newly-fetched remote branch appear in the merge-target selector")
def test_target_branch_selector_updates_when_remote_ref_added(sculptor_instance_: SculptorInstance) -> None:
    """A new remote-tracking ref should surface in the target-branch selector.

    A real ``git fetch`` of a new upstream branch writes a ref under
    ``refs/remotes``; ``git update-ref`` reproduces that effect locally with no
    network. The scanner should notice the changed remote refs, recompute the
    repo's target branches once, and push them — so the new branch appears in
    the open selector.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_WRITE_FILE_PROMPT, mode="CLONE", backend_url=sculptor_instance_.backend_api_url
    )
    wait_for_completed_message_count(chat_panel=task_page.get_chat_panel(), expected_message_count=2)

    # Open the selector and confirm the auto-resolved remote is already listed.
    selector = task_page.get_target_branch_selector()
    expect(selector).to_be_visible()
    selector.click()
    expect(page.get_by_placeholder("Search branches...")).to_be_visible()
    expect(task_page.get_target_branch_options().filter(has_text="origin/main")).to_be_visible()

    # Create a new remote-tracking ref the way a fetch would, without a network.
    workspace_dir = _get_workspace_working_dir(sculptor_instance_)
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/freshly-fetched", "origin/main"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    # With the selector still open, the new branch should appear live once the
    # scanner detects the changed remote refs and pushes the updated list.
    expect(task_page.get_target_branch_options().filter(has_text="origin/freshly-fetched")).to_be_visible()
