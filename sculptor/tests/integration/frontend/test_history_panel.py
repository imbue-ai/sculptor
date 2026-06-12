"""Integration tests for the History panel.

Tests verify that the History panel shows commit history, expanding commits
reveals changed files, and clicking files opens commit-scoped diffs.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _extract_workspace_id(url: str) -> str:
    """Extract the workspace ID from a Sculptor URL (format: /ws/{workspaceID}/agent/...)."""
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    if not match:
        raise ValueError(f"Could not extract workspace ID from URL: {url}")
    return match.group(1)


_TWO_COMMITS_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "first.py",
        "content": "x = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add first.py'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "second.py",
        "content": "y = 2\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add second.py'"
      }
    }
  ]
}`"""


@user_story("to see commit history in the History panel")
def test_history_panel_shows_commits(sculptor_instance_: SculptorInstance) -> None:
    """The History panel should show commits on the current branch."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_TWO_COMMITS_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Should show both commit messages
    expect(history_panel).to_contain_text("Add second.py")
    expect(history_panel).to_contain_text("Add first.py")


_CREATE_BRANCH_PROMPT = """\
fake_claude:bash `{"command": "git checkout -b feature"}`"""

_COMMIT_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "new_feature.py",
        "content": "print('hello')\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add new feature'"
      }
    }
  ]
}`"""


@user_story("to see the History panel update dynamically after a commit")
def test_history_panel_updates_after_commit(sculptor_instance_: SculptorInstance) -> None:
    """The History panel should show new commits without a page refresh."""
    page = sculptor_instance_.page

    # Create a workspace with a feature branch but no commits yet
    task_page = start_task_and_wait_for_ready(page, prompt=_CREATE_BRANCH_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Ensure the Files panel is open, then switch to the History tab — should show branch start
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()
    expect(history_panel).to_contain_text("start of branch")

    # Now tell the agent to make a commit via a follow-up message
    send_chat_message(chat_panel, _COMMIT_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)

    # The History panel should dynamically update to show the new commit
    expect(history_panel).to_contain_text("Add new feature")


_TARGET_BRANCH_CHANGE_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-tb-test"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "alpha.py",
        "content": "a = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add alpha.py'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "beta.py",
        "content": "b = 2\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add beta.py'"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git push origin feature-tb-test"
      }
    }
  ]
}`"""


@user_story("to see the History panel refresh when the target branch changes")
def test_history_panel_refreshes_on_target_branch_change(sculptor_instance_: SculptorInstance) -> None:
    """Changing the target branch should trigger a history refetch so the commit
    list reflects the new fork-point."""
    page = sculptor_instance_.page

    # Create a branch with 2 commits and push it to origin. Clone mode is
    # required because the agent pushes to ``origin`` and the test later
    # references ``origin/feature-tb-test`` — neither exists in a worktree.
    task_page = start_task_and_wait_for_ready(
        page, prompt=_TARGET_BRANCH_CHANGE_PROMPT, wait_for_agent_to_finish=False, mode="CLONE"
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open the History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Both commits should be visible (fork-point is origin/main).
    expect(history_panel).to_contain_text("Add alpha.py")
    expect(history_panel).to_contain_text("Add beta.py")

    # Read HEAD's short hash from the commits API so we can assert the terminus
    # moves to HEAD after the target-branch change.
    workspace_id = _extract_workspace_id(page.url)
    base_url = page.url.split("#")[0].rstrip("/")
    pre_patch = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}/commits")
    assert pre_patch.ok, f"Failed to read commits: {pre_patch.status}"
    head_short_hash = pre_patch.json()["commits"][0]["hash"][:11]

    # Change the target branch to the branch we just pushed.  Since we pushed
    # the same commits as HEAD, merge-base(HEAD, origin/feature-tb-test) = HEAD,
    # so there are zero commits since the fork-point.
    response = page.request.patch(
        f"{base_url}/api/v1/workspaces/{workspace_id}",
        data={"target_branch": "origin/feature-tb-test"},
    )
    assert response.ok, f"Failed to update target branch: {response.status}"

    # The History panel should refresh: the terminus indicator should show
    # HEAD as the new fork-point (it only renders in the success state, so
    # this implicitly waits past the transient loading state and confirms
    # the panel rendered fresh data).  Once the fork-point has moved, no
    # commit entries should remain.
    terminus = history_panel.get_terminus()
    expect(terminus).to_contain_text(f"({head_short_hash})", timeout=30_000)
    expect(history_panel.get_commit_entries()).to_have_count(0)


_ONE_COMMIT_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-terminus-test"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "feature.py",
        "content": "x = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add feature.py'"
      }
    }
  ]
}`"""


@user_story("to see the terminus indicator with a fork-point hash in the history panel")
def test_terminus_shows_fork_point_hash(sculptor_instance_: SculptorInstance) -> None:
    """The terminus indicator should show 'start of branch' with an abbreviated
    commit hash in parentheses, indicating the fork point."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_ONE_COMMIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # The terminus indicator should be visible
    terminus = history_panel.get_terminus()
    expect(terminus).to_be_visible()

    # Should show "start of branch" with a hash in parentheses
    expect(terminus).to_contain_text("start of branch")
    # The hash should be an abbreviated hex string (at least 7 chars)
    expect(terminus).to_contain_text(re.compile(r"\([0-9a-f]{7,}\)"))


@user_story("to see the terminus indicator even when there are no commits on the branch")
def test_terminus_visible_with_no_commits(sculptor_instance_: SculptorInstance) -> None:
    """When a fresh branch has no commits, the terminus indicator should still
    be visible, showing 'start of branch'."""
    page = sculptor_instance_.page

    prompt = 'fake_claude:bash `{"command": "git checkout -b empty-branch-test"}`'
    task_page = start_task_and_wait_for_ready(page, prompt=prompt, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    terminus = history_panel.get_terminus()
    expect(terminus).to_be_visible()
    expect(terminus).to_contain_text("start of branch")


_MERGE_COMMIT_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-merge-test"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "base.py",
        "content": "x = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add base.py on feature branch'"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b side-branch"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "side.py",
        "content": "y = 2\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add side.py on side branch'"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git checkout feature-merge-test"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "main_line.py",
        "content": "z = 3\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add main_line.py on feature branch'"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git merge side-branch --no-ff -m 'Merge side-branch into feature'"
      }
    }
  ]
}`"""


@user_story("to see merge commit spur visualization in the history panel")
def test_merge_commit_shows_spur(sculptor_instance_: SculptorInstance) -> None:
    """When a merge commit exists in the history, expanding it should show
    a merge spur row indicating the second parent branch."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_MERGE_COMMIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # The merge commit message should be visible
    expect(history_panel).to_contain_text("Merge side-branch into feature")

    # Click the merge commit to expand it
    merge_entry = history_panel.get_commit_entry_by_text("Merge side-branch into feature")
    expect(merge_entry).to_be_visible()
    merge_entry.click()

    # After expanding a merge commit, the merge spur should be visible
    merge_spur = history_panel.get_merge_spur()
    expect(merge_spur).to_be_visible()

    # All commits should be visible in the history
    expect(history_panel).to_contain_text("Add main_line.py on feature branch")
    expect(history_panel).to_contain_text("Add base.py on feature branch")


@user_story("to see commit metadata (diff stats, relative time, hash) below each commit message")
def test_commit_entry_shows_metadata_line(sculptor_instance_: SculptorInstance) -> None:
    """Each commit entry should show a second line with diff stats, file count,
    relative time, and short hash."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_TWO_COMMITS_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Find the commit entry for "Add second.py" and check its metadata line
    commit_entry = history_panel.get_commit_entry_by_text("Add second.py")
    expect(commit_entry).to_be_visible()

    meta = history_panel.get_commit_meta(commit_entry)
    expect(meta).to_be_visible()

    # Metadata should contain diff stats, file count, and a short hex hash
    expect(meta).to_contain_text("1 file")
    expect(meta).to_contain_text("+")
    expect(meta).to_contain_text(re.compile(r"[0-9a-f]{7}"))


@user_story("to see full commit details in a popover when hovering over a commit")
def test_commit_hover_popover_shows_details(sculptor_instance_: SculptorInstance) -> None:
    """Hovering over a commit entry should show a popover with the full message,
    author, date, commit id, and change stats."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_TWO_COMMITS_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Hover over the first commit entry to trigger the popover
    first_commit = history_panel.get_commit_entries().first
    history_panel.get_commit_message(first_commit).hover()

    # The popover should appear (uses the page-level locator since HoverCard
    # renders via a portal outside the commit entry)
    popover = history_panel.get_commit_popover()
    expect(popover).to_be_visible()

    # Popover should contain key metadata fields
    expect(popover).to_contain_text("Author")
    expect(popover).to_contain_text("Date")
    expect(popover).to_contain_text("Commit id")
    expect(popover).to_contain_text("Add second.py")


@user_story("to dismiss the commit popover when clicking to expand a commit")
def test_click_dismisses_popover(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a commit entry to expand it should dismiss the hover popover,
    not show both the expanded details and the popover simultaneously."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_TWO_COMMITS_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Hover to open the popover, then click to expand
    first_commit = history_panel.get_commit_entries().first
    commit_message = history_panel.get_commit_message(first_commit)
    commit_message.hover()

    popover = history_panel.get_commit_popover()
    expect(popover).to_be_visible()

    # Click to expand — popover should dismiss
    commit_message.click()
    expect(popover).not_to_be_visible()


# Rename an entire folder so git reports the change using the compact
# {old => new}/file notation in --numstat output.
_FOLDER_RENAME_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-folder-rename"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git mv src lib && git add -A && git commit -m 'Rename src to lib'"
      }
    }
  ]
}`"""


@user_story("to see renamed folder files with correct paths in the history panel")
def test_folder_rename_shows_correct_paths(sculptor_instance_: SculptorInstance) -> None:
    """Renaming a folder should show files under the new folder name, not git's
    compact {old => new} rename notation.

    When git log --numstat -M reports renames using the {old => new}/file.py
    format, the backend must expand these into proper paths so the UI renders
    the files under their actual new folder name.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_FOLDER_RENAME_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Click the rename commit to expand its file list
    rename_entry = history_panel.get_commit_entry_by_text("Rename src to lib")
    expect(rename_entry).to_be_visible()
    rename_entry.click()

    # The expanded file list should show files under "lib", not "{src => lib}"
    expect(rename_entry).to_contain_text("lib")
    expect(rename_entry).not_to_contain_text("{src => lib}")
    expect(rename_entry).not_to_contain_text("=>")


# Rename both a single file and a folder (containing multiple files) in one commit.
# The single-file rename uses `git mv` directly; the folder rename moves
# all remaining files from src/ to lib/.
_RENAME_WITH_CONTENT_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-rename-diff"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git mv stuff.txt notes.txt && git mv src lib && git add -A && git commit -m 'Rename file and folder'"
      }
    }
  ]
}`"""


@user_story("to see a rename banner when clicking a renamed file in the commits tab")
def test_clicking_renamed_file_in_commits_shows_rename_banner(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a renamed file in the Commits tab should show a rename banner.

    When a file is renamed (either directly or as part of a folder rename),
    clicking it in the History panel should open a diff panel that shows
    a rename banner with the old and new paths, not an empty panel.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_RENAME_WITH_CONTENT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open History tab
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    # Expand the rename commit
    rename_entry = history_panel.get_commit_entry_by_text("Rename file and folder")
    expect(rename_entry).to_be_visible()
    rename_entry.click()

    # Click the directly-renamed file (stuff.txt -> notes.txt)
    notes_row = history_panel.get_tree_rows(rename_entry).filter(has_text="notes.txt")
    expect(notes_row).to_be_visible()
    notes_row.click()

    # The diff panel should show a rename banner with the old and new paths
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    rename_banner = diff_panel.get_rename_banner()
    expect(rename_banner).to_be_visible()
    expect(rename_banner).to_contain_text("stuff.txt")
    expect(rename_banner).to_contain_text("notes.txt")

    # Click a file from the renamed folder (src/helpers.py -> lib/helpers.py)
    helpers_row = history_panel.get_tree_rows(rename_entry).filter(has_text="helpers.py")
    expect(helpers_row).to_be_visible()
    helpers_row.click()

    # The diff panel should also show a rename banner for the folder rename
    expect(rename_banner).to_be_visible()
    expect(rename_banner).to_contain_text("src/helpers.py")
    expect(rename_banner).to_contain_text("lib/helpers.py")
