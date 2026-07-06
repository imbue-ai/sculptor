"""Integration tests for the Commits panel — the commit-history browser paired
with its own embedded DiffViewer.

The Commits panel is one of the three separate panels that replaced the old
single File-Browser panel with its All/Changes/History tabs. It pairs the
commit history (the graph terminus, commit rows, the merge spur, the per-commit
hover popover, and a commit's expanded per-file rows) with an always-visible
embedded viewer via the shared ``ExplorerLayout``. There is no tab model: the
Files and Changes panels are their own panels.

These cases are MIGRATED, not rewritten, from the pre-rewrite History-tab tests.
The proven assertions carry over unchanged; only
the *surface* moved:

* a panel is opened through the section ``+`` add-panel dropdown (the shared
  ``open_panel`` helper) instead of clicking the File-Browser History tab;
* the terminus, commit rows, merge spur, popover, metadata, and per-commit file
  rows are driven through the ``PlaywrightCommitsPanelElement`` POM scoped to the
  opened section, and clicking a commit's file opens its commit-scoped diff into
  the panel's OWN embedded viewer rather than a page-wide active diff.

The Commits panel is seeded into the (collapsed-by-default) LEFT section, so
``_open_commits_panel_with`` reveals it there while the agent chat stays mounted
in the CENTER section. These history assertions are read-only; the one test that
sends a follow-up commit types into the still-mounted chat, then re-activates the
Commits tab to read the refreshed history.

The old page-wide multi-tab diff surface (commit-diff tabs coexisting with
Changes-panel "regular" diff tabs in a shared tab bar, tab re-selection, and
middle-click tab close) is NOT part of the Commits panel: each panel embeds its
OWN single viewer with its own selection, so the tab-coexistence kernels are
retired with that surface. Their commit-scoped diff CONTENT — the part that
proves a commit file opens the right committed diff — is migrated against the
embedded viewer.

The commit-graph DOT VISUALS (gray / green = HEAD / amber-ring = uncommitted)
are screenshot-verified, not asserted as layout/color properties, so no test
reads a computed color or style here.

Migrated from:
* ``test_history_panel.py``
* ``test_history_panel_diffs.py``
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.commits_panel import PlaywrightCommitsPanelElement
from sculptor.testing.elements.commits_panel import get_commits_panel_in
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Number of leading hash characters the terminus indicator renders for the
# fork-point commit. Must match ``SHORT_HASH_LENGTH`` in
# ``frontend/src/pages/workspace/panels/historyPanel/commitGraph.ts``; the
# terminus assertion abbreviates the fork-point hash with this same width.
_TERMINUS_SHORT_HASH_LENGTH = 11

# --------------------------------------------------------------------------- #
# FakeClaude prompts (migrated verbatim from the source tests).
# --------------------------------------------------------------------------- #

# Two commits on a feature branch, each adding one file.
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

# Create a feature branch with no commits yet.
_CREATE_BRANCH_PROMPT = """\
fake_claude:bash `{"command": "git checkout -b feature"}`"""

# Write a file and commit it (sent as a follow-up message).
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

# Two commits on a pushed feature branch (so origin/feature-tb-test exists with
# the same commits as HEAD); pointing the target branch there yields no commits.
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

# One commit on a feature branch (for the terminus fork-point assertion).
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

# A fresh branch with no commits (for the terminus-with-no-commits assertion).
_EMPTY_BRANCH_PROMPT = 'fake_claude:bash `{"command": "git checkout -b empty-branch-test"}`'

# A feature branch with a merge commit (--no-ff merge of a side branch), so the
# history has a merge node whose expansion reveals a merge spur.
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

# Rename both a single file and a folder (containing multiple files) in one
# commit. The single-file rename uses `git mv` directly; the folder rename moves
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

# A branch with a single commit touching TWO files (alpha.py + beta.py).
_MULTI_FILE_COMMIT_PROMPT = """\
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
        "file_path": "alpha.py",
        "content": "a = 1\\n"
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
        "command": "git add -A && git commit -m 'Add alpha and beta'"
      }
    }
  ]
}`"""

# A branch that commits shared.py, then leaves an uncommitted edit to it, so the
# commit-scoped diff (x = 1) differs from the working tree (x = 2).
_COMMIT_THEN_EDIT_PROMPT = """\
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
        "file_path": "shared.py",
        "content": "x = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add shared.py'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "shared.py",
        "content": "x = 2\\n"
      }
    }
  ]
}`"""

# Two commits that both modify the SAME file (shared.py): commit 1 adds it,
# commit 2 modifies it.
_SAME_FILE_TWO_COMMITS_PROMPT = """\
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
        "file_path": "shared.py",
        "content": "version_one = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add shared.py v1'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "shared.py",
        "content": "version_two = 2\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Update shared.py v2'"
      }
    }
  ]
}`"""

# Two separate commits, each touching a different file.
_TWO_SINGLE_FILE_COMMITS_PROMPT = """\
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

# A text-only task (FakeClaude's default response, no tool calls): the agent
# touches no files, so no diff chips render in chat and Pierre's shared syntax
# highlighter stays COLD until the Commits panel renders the session's first
# diff. Prompts that use ``write_file`` warm the highlighter through the chat's
# file-edit chips, which masks cold-start rendering bugs.
_TEXT_ONLY_PROMPT = "Say hello"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _open_commits_panel_with(
    page: Page, prompt: str, *, mode: str | None = None
) -> tuple[PlaywrightTaskPage, PlaywrightCommitsPanelElement]:
    """Run a FakeClaude prompt, wait for it, then open the Commits panel.

    Returns the task page and the Commits panel POM scoped to the LEFT section,
    where the Commits panel is seeded. Revealing it there leaves the agent chat
    mounted in the center, so read-only history assertions and follow-up chat
    messages both work without remounting anything. The message count is awaited
    BEFORE opening the panel.
    """
    task_page = start_task_and_wait_for_ready(page, prompt=prompt, wait_for_agent_to_finish=False, mode=mode)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)
    section_root = open_panel(page, "commits", sub_section="left")
    return task_page, get_commits_panel_in(section_root, page)


def _reactivate_commits_panel(page: Page) -> PlaywrightCommitsPanelElement:
    """Re-activate the Commits tab so the panel remounts after switching to chat.

    A single-instance panel that is already open is dropped from the add-panel
    dropdown's re-add list, so re-opening it that way would fail. The Commits panel
    is seeded into the (collapsed-by-default) LEFT section; ``_open_commits_panel_with``
    already expanded it, so this re-expands it (idempotent) and clicks its LEFT-section
    panel tab to make the already-open Commits panel active again.
    """
    left_section = PlaywrightWorkspaceSection(page, "left")
    left_section.expand_section()
    commits_tab = left_section.get_panel_tab("commits")
    expect(commits_tab).to_be_visible()
    commits_tab.click()
    section_root = left_section.get_section()
    expect(section_root).to_be_visible()
    return get_commits_panel_in(section_root, page)


# --------------------------------------------------------------------------- #
# Migrated: test_history_panel.py
# --------------------------------------------------------------------------- #


@user_story("to see commit history in the Commits panel")
def test_history_panel_shows_commits(sculptor_instance_: SculptorInstance) -> None:
    """The Commits panel should show commits on the current branch."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _TWO_COMMITS_PROMPT)

    commits_list = commits_panel.get_list()
    expect(commits_list).to_be_visible()

    # Should show both commit messages.
    expect(commits_list).to_contain_text("Add second.py")
    expect(commits_list).to_contain_text("Add first.py")


@user_story("to see the Commits panel update dynamically after a commit")
def test_history_panel_updates_after_commit(sculptor_instance_: SculptorInstance) -> None:
    """The Commits panel should show new commits without a page refresh.

    The follow-up commit is sent via the chat — still mounted in the center while
    Commits is revealed in the left — then the Commits panel is re-activated to
    read the refreshed history.
    """
    page = sculptor_instance_.page

    # Create a workspace with a feature branch but no commits yet.
    task_page, commits_panel = _open_commits_panel_with(page, _CREATE_BRANCH_PROMPT)

    # With no commits yet, the panel shows the branch start.
    commits_list = commits_panel.get_list()
    expect(commits_list).to_be_visible()
    expect(commits_list).to_contain_text("start of branch")

    # Tell the agent to make a commit via a follow-up message. The chat stays
    # mounted in the center, so it can receive the message directly.
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel, _COMMIT_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)

    # Re-activate the Commits panel — it should show the new commit.
    commits_panel = _reactivate_commits_panel(page)
    expect(commits_panel.get_list()).to_contain_text("Add new feature")


@user_story("to see the Commits panel refresh when the target branch changes")
def test_history_panel_refreshes_on_target_branch_change(sculptor_instance_: SculptorInstance) -> None:
    """Changing the target branch should trigger a history refetch so the commit
    list reflects the new fork-point."""
    page = sculptor_instance_.page

    # Create a branch with 2 commits and push it to origin. Clone mode is
    # required because the agent pushes to ``origin`` and the test later
    # references ``origin/feature-tb-test`` — neither exists in a worktree.
    task_page, commits_panel = _open_commits_panel_with(page, _TARGET_BRANCH_CHANGE_PROMPT, mode="CLONE")

    commits_list = commits_panel.get_list()
    expect(commits_list).to_be_visible()

    # Both commits should be visible (fork-point is origin/main).
    expect(commits_list).to_contain_text("Add alpha.py")
    expect(commits_list).to_contain_text("Add beta.py")

    # Read HEAD's short hash from the commits API so we can assert the terminus
    # moves to HEAD after the target-branch change.
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", page.url)
    assert match, f"Could not extract workspace ID from URL: {page.url}"
    workspace_id = match.group(1)
    base_url = sculptor_instance_.backend_api_url.rstrip("/")
    pre_patch = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}/commits")
    assert pre_patch.ok, f"Failed to read commits: {pre_patch.status}"
    head_short_hash = pre_patch.json()["commits"][0]["hash"][:_TERMINUS_SHORT_HASH_LENGTH]

    # Change the target branch to the branch we just pushed. Since we pushed the
    # same commits as HEAD, merge-base(HEAD, origin/feature-tb-test) = HEAD, so
    # there are zero commits since the fork-point.
    response = page.request.patch(
        f"{base_url}/api/v1/workspaces/{workspace_id}",
        data={"target_branch": "origin/feature-tb-test"},
    )
    assert response.ok, f"Failed to update target branch: {response.status}"

    # The Commits panel should refresh: the terminus indicator should show HEAD
    # as the new fork-point (it only renders in the success state, so this
    # implicitly waits past the transient loading state and confirms the panel
    # rendered fresh data). Once the fork-point has moved, no commit entries
    # should remain.
    terminus = commits_panel.get_terminus()
    expect(terminus).to_contain_text(f"({head_short_hash})", timeout=30_000)
    expect(commits_panel.get_commit_entries()).to_have_count(0)


@user_story("to see the terminus indicator with a fork-point hash in the Commits panel")
def test_terminus_shows_fork_point_hash(sculptor_instance_: SculptorInstance) -> None:
    """The terminus indicator should show 'start of branch' with an abbreviated
    commit hash in parentheses, indicating the fork point."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _ONE_COMMIT_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # The terminus indicator should be visible.
    terminus = commits_panel.get_terminus()
    expect(terminus).to_be_visible()

    # Should show "start of branch" with a hash in parentheses.
    expect(terminus).to_contain_text("start of branch")
    # The hash should be an abbreviated hex string (at least 7 chars).
    expect(terminus).to_contain_text(re.compile(r"\([0-9a-f]{7,}\)"))


@user_story("to see the terminus indicator even when there are no commits on the branch")
def test_terminus_visible_with_no_commits(sculptor_instance_: SculptorInstance) -> None:
    """When a fresh branch has no commits, the terminus indicator should still
    be visible, showing 'start of branch'."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _EMPTY_BRANCH_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    terminus = commits_panel.get_terminus()
    expect(terminus).to_be_visible()
    expect(terminus).to_contain_text("start of branch")


@user_story("to see merge commit spur visualization in the Commits panel")
def test_merge_commit_shows_spur(sculptor_instance_: SculptorInstance) -> None:
    """When a merge commit exists in the history, expanding it should show
    a merge spur row indicating the second parent branch."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _MERGE_COMMIT_PROMPT)

    commits_list = commits_panel.get_list()
    expect(commits_list).to_be_visible()

    # The merge commit message should be visible.
    expect(commits_list).to_contain_text("Merge side-branch into feature")

    # Click the merge commit to expand it.
    merge_entry = commits_panel.get_commit_entry_by_text("Merge side-branch into feature")
    expect(merge_entry).to_be_visible()
    merge_entry.click()

    # After expanding a merge commit, the merge spur should be visible.
    merge_spur = commits_panel.get_merge_spur()
    expect(merge_spur).to_be_visible()

    # All commits should be visible in the history.
    expect(commits_list).to_contain_text("Add main_line.py on feature branch")
    expect(commits_list).to_contain_text("Add base.py on feature branch")


@user_story("to see commit metadata (diff stats, relative time, hash) below each commit message")
def test_commit_entry_shows_metadata_line(sculptor_instance_: SculptorInstance) -> None:
    """Each commit entry should show a second line with diff stats, file count,
    relative time, and short hash."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _TWO_COMMITS_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # Find the commit entry for "Add second.py" and check its metadata line.
    commit_entry = commits_panel.get_commit_entry_by_text("Add second.py")
    expect(commit_entry).to_be_visible()

    meta = commits_panel.get_commit_meta(commit_entry)
    expect(meta).to_be_visible()

    # Metadata should contain diff stats, file count, and a short hex hash.
    expect(meta).to_contain_text("1 file")
    expect(meta).to_contain_text("+")
    expect(meta).to_contain_text(re.compile(r"[0-9a-f]{7}"))


@user_story("to see full commit details in a popover when hovering over a commit")
def test_commit_hover_popover_shows_details(sculptor_instance_: SculptorInstance) -> None:
    """Hovering over a commit entry should show a popover with the full message,
    author, date, commit id, and change stats."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _TWO_COMMITS_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # Hover over the first commit entry to trigger the popover.
    first_commit = commits_panel.get_commit_entries().first
    commits_panel.get_commit_message(first_commit).hover()

    # The popover should appear (uses the page-level locator since HoverCard
    # renders via a portal outside the commit entry).
    popover = commits_panel.get_commit_popover()
    expect(popover).to_be_visible()

    # Popover should contain key metadata fields.
    expect(popover).to_contain_text("Author")
    expect(popover).to_contain_text("Date")
    expect(popover).to_contain_text("Commit id")
    expect(popover).to_contain_text("Add second.py")


@user_story("to dismiss the commit popover when clicking to expand a commit")
def test_click_dismisses_popover(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a commit entry to expand it should dismiss the hover popover,
    not show both the expanded details and the popover simultaneously."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _TWO_COMMITS_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # Hover to open the popover, then click to expand.
    first_commit = commits_panel.get_commit_entries().first
    commit_message = commits_panel.get_commit_message(first_commit)
    commit_message.hover()

    popover = commits_panel.get_commit_popover()
    expect(popover).to_be_visible()

    # Click to expand — popover should dismiss.
    commit_message.click()
    expect(popover).not_to_be_visible()


@user_story("to see renamed folder files with correct paths in the Commits panel")
def test_folder_rename_shows_correct_paths(sculptor_instance_: SculptorInstance) -> None:
    """Renaming a folder should show files under the new folder name, not git's
    compact {old => new} rename notation.

    When git log --numstat -M reports renames using the {old => new}/file.py
    format, the backend must expand these into proper paths so the UI renders
    the files under their actual new folder name.
    """
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _FOLDER_RENAME_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # Click the rename commit to expand its file list.
    rename_entry = commits_panel.get_commit_entry_by_text("Rename src to lib")
    expect(rename_entry).to_be_visible()
    rename_entry.click()

    # Wait for the expanded file rows to render before asserting on their text —
    # otherwise the negative "=>" assertions pass vacuously against the
    # not-yet-expanded commit entry.
    expect(commits_panel.get_tree_rows(rename_entry).first).to_be_visible()

    # The expanded file list should show files under "lib", not "{src => lib}".
    expect(rename_entry).to_contain_text("lib")
    expect(rename_entry).not_to_contain_text("{src => lib}")
    expect(rename_entry).not_to_contain_text("=>")


@user_story("to see a rename banner when clicking a renamed file in the Commits panel")
def test_clicking_renamed_file_in_commits_shows_rename_banner(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a renamed file in the Commits panel should show a rename banner.

    When a file is renamed (either directly or as part of a folder rename),
    clicking it in the Commits panel should open the embedded viewer with a rename
    banner showing the old and new paths, not an empty viewer.
    """
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _RENAME_WITH_CONTENT_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # Expand the rename commit.
    rename_entry = commits_panel.get_commit_entry_by_text("Rename file and folder")
    expect(rename_entry).to_be_visible()
    rename_entry.click()

    # Click the directly-renamed file (stuff.txt -> notes.txt).
    notes_row = commits_panel.get_tree_rows(rename_entry).filter(has_text="notes.txt")
    expect(notes_row).to_be_visible()
    notes_row.click()

    # The embedded viewer should show a rename banner with the old and new paths.
    viewer = commits_panel.get_diff_viewer()
    rename_banner = viewer.get_rename_banner()
    expect(rename_banner).to_be_visible()
    expect(rename_banner).to_contain_text("stuff.txt")
    expect(rename_banner).to_contain_text("notes.txt")

    # Click a file from the renamed folder (src/helpers.py -> lib/helpers.py).
    helpers_row = commits_panel.get_tree_rows(rename_entry).filter(has_text="helpers.py")
    expect(helpers_row).to_be_visible()
    helpers_row.click()

    # The embedded viewer should also show a rename banner for the folder rename.
    expect(rename_banner).to_be_visible()
    expect(rename_banner).to_contain_text("src/helpers.py")
    expect(rename_banner).to_contain_text("lib/helpers.py")


# --------------------------------------------------------------------------- #
# Migrated: test_history_panel_diffs.py
#
# Each commit-scoped diff renders in the Commits panel's OWN embedded viewer
#: clicking a commit's file replaces the viewer's content. The
# page-wide multi-tab kernels (commit-diff tabs coexisting with Changes-panel
# regular tabs, tab re-selection, middle-click close) belong to the retired
# tab-bar surface and are skipped below; their diff CONTENT is migrated here.
# --------------------------------------------------------------------------- #


def _open_commits_and_expand_first_commit(page: Page, prompt: str) -> tuple[PlaywrightCommitsPanelElement, Locator]:
    """Open the Commits panel and expand the first (most recent) commit.

    Returns a tuple of (commits_panel_pom, commit_entry).
    """
    _, commits_panel = _open_commits_panel_with(page, prompt)
    expect(commits_panel.get_list()).to_be_visible()

    first_commit = commits_panel.get_commit_entries().first
    commits_panel.get_commit_message(first_commit).click()
    return commits_panel, first_commit


@user_story("to view a single file's diff from a multi-file commit without the diff viewer crashing")
def test_click_file_in_multi_file_commit(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file inside a commit that has 2+ changed files should open
    that file's commit-scoped diff without crashing."""
    page = sculptor_instance_.page
    commits_panel, first_commit = _open_commits_and_expand_first_commit(page, _MULTI_FILE_COMMIT_PROMPT)

    # The commit has two files: alpha.py and beta.py.  Click alpha.py.
    file_rows = commits_panel.get_tree_rows(first_commit)
    expect(file_rows).to_have_count(2)

    alpha_row = commits_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    # The embedded viewer should show the file's commit-scoped diff — NOT an
    # error or blank screen.
    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("alpha.py")
    expect(viewer).to_contain_text("a = 1")


@user_story("to open a committed file as the session's first diff and see its content")
def test_first_commit_file_open_renders_diff_with_cold_highlighter(sculptor_instance_: SculptorInstance) -> None:
    """The FIRST diff rendered in a page session must paint its content.

    The diff body is rendered by Pierre, whose shared syntax highlighter loads
    asynchronously on the session's first render. A workspace whose agent made
    no file edits (text-only reply → no diff chips in chat) reaches the Commits
    panel with that highlighter still cold, so clicking a commit file here
    exercises the cold-start path directly: the viewer must not stay blank
    while (or after) the highlighter loads.

    The dev-only StrictMode variant of this cold start (the remounted Pierre
    instance mistaking the aborted first mount's empty ``<pre>`` for
    prerendered content and never rendering) cannot manifest here — this
    harness serves the production bundle, where StrictMode does not remount —
    and is locked in by ``PierreDiffView.test.tsx`` instead. This test guards
    the production-bundle half: a cold first render must still end up painting
    the diff body, not just the header (which renders its stats from the
    parsed diff even while the body is blank).

    Uses the mock repo's pre-existing "Stuff" commit so the agent never touches
    a file before the click.
    """
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _TEXT_ONLY_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    # Expand the pre-existing "Stuff" commit and click its single file.
    stuff_commit = commits_panel.get_commit_entry_by_text("Stuff")
    commits_panel.get_commit_message(stuff_commit).click()
    stuff_row = commits_panel.get_tree_rows(stuff_commit).filter(has_text="stuff.txt")
    expect(stuff_row).to_be_visible()
    stuff_row.click()

    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("stuff.txt")
    # The BODY must paint the committed content — the header alone is not
    # enough, because it renders its stats from the parsed diff even while the
    # body is blank.
    expect(viewer.get_unified_diff_views()).to_contain_text("stuff")


@user_story("to open diffs from two different commits and see each commit's content")
def test_open_files_from_different_commits(sculptor_instance_: SculptorInstance) -> None:
    """Opening files from two different commits should each show that commit's
    diff content in the embedded viewer.

    The retired page-wide surface kept a separate tab per commit-diff; the Commits
    panel's single embedded viewer instead replaces its content on each open, so
    this migrates the per-commit content assertions (there is no tab bar left to
    assert coexistence / re-selection against).
    """
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _TWO_SINGLE_FILE_COMMITS_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    commits = commits_panel.get_commit_entries()
    # The mock repo has 2 pre-existing commits on the testing branch (app.py,
    # stuff.txt) plus the 2 agent-created commits = 4 total since main.
    expect(commits).to_have_count(4)

    # Expand and click the file in the first (most recent) commit: "Add second.py"
    first_commit = commits.nth(0)
    commits_panel.get_commit_message(first_commit).click()
    second_py_row = commits_panel.get_tree_rows(first_commit).filter(has_text="second.py")
    expect(second_py_row).to_be_visible()
    second_py_row.click()

    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("second.py")
    expect(viewer).to_contain_text("y = 2")

    # Expand and click the file in the second commit: "Add first.py"
    second_commit = commits.nth(1)
    commits_panel.get_commit_message(second_commit).click()
    first_py_row = commits_panel.get_tree_rows(second_commit).filter(has_text="first.py")
    expect(first_py_row).to_be_visible()
    first_py_row.click()

    # The embedded viewer now shows the second commit's file content.
    viewer.assert_diff_shows("first.py")
    expect(viewer).to_contain_text("x = 1")


@user_story("to view the correct diff content when the same file is modified across two commits")
def test_same_file_two_commits_shows_correct_content(sculptor_instance_: SculptorInstance) -> None:
    """When the same file is changed in two commits, opening it from each commit
    should show that commit's diff in the embedded viewer — not the other
    commit's diff."""
    page = sculptor_instance_.page
    _, commits_panel = _open_commits_panel_with(page, _SAME_FILE_TWO_COMMITS_PROMPT)

    expect(commits_panel.get_list()).to_be_visible()

    commits = commits_panel.get_commit_entries()
    # The mock repo has 2 pre-existing commits on the testing branch (app.py,
    # stuff.txt) plus the 2 agent-created commits = 4 total since main.
    expect(commits).to_have_count(4)

    # Commit 0 (most recent): "Update shared.py v2" — modifies shared.py
    # Commit 1 (older): "Add shared.py v1" — adds shared.py
    v2_commit = commits.nth(0)
    v1_commit = commits.nth(1)

    # Open shared.py from the v2 commit (modification diff) — shows version_two.
    commits_panel.get_commit_message(v2_commit).click()
    v2_file_row = commits_panel.get_tree_rows(v2_commit).filter(has_text="shared.py")
    expect(v2_file_row).to_be_visible()
    v2_file_row.click()

    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("shared.py")
    expect(viewer).to_contain_text("version_two")

    # Open shared.py from the v1 commit (addition diff) — shows version_one.
    commits_panel.get_commit_message(v1_commit).click()
    v1_file_row = commits_panel.get_tree_rows(v1_commit).filter(has_text="shared.py")
    expect(v1_file_row).to_be_visible()
    v1_file_row.click()

    viewer.assert_diff_shows("shared.py")
    expect(viewer).to_contain_text("version_one")


@user_story("to switch between different file diffs within the same commit")
def test_switch_files_within_same_commit(sculptor_instance_: SculptorInstance) -> None:
    """Opening two files from the same commit should each show that file's
    individual diff in the embedded viewer."""
    page = sculptor_instance_.page
    commits_panel, first_commit = _open_commits_and_expand_first_commit(page, _MULTI_FILE_COMMIT_PROMPT)

    # Open alpha.py — shows a = 1.
    alpha_row = commits_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("alpha.py")
    expect(viewer).to_contain_text("a = 1")

    # Open beta.py from the same commit — shows b = 2.
    beta_row = commits_panel.get_tree_rows(first_commit).filter(has_text="beta.py")
    expect(beta_row).to_be_visible()
    beta_row.click()

    viewer.assert_diff_shows("beta.py")
    expect(viewer).to_contain_text("b = 2")

    # Re-open alpha.py — the viewer shows alpha's content again, not beta's.
    alpha_row.click()
    viewer.assert_diff_shows("alpha.py")
    expect(viewer).to_contain_text("a = 1")


@user_story("to see correct line count stats in the file header for a commit-scoped diff")
def test_commit_diff_file_header_shows_line_counts(sculptor_instance_: SculptorInstance) -> None:
    """The file header above a commit-scoped diff should display the actual
    added/removed line counts from the commit, not +0 -0."""
    page = sculptor_instance_.page
    commits_panel, first_commit = _open_commits_and_expand_first_commit(page, _MULTI_FILE_COMMIT_PROMPT)

    # Click alpha.py — a file with 1 added line ("a = 1\n").
    alpha_row = commits_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    # The embedded viewer's file header should show +1 (1 added line), not +0.
    viewer = commits_panel.get_diff_viewer()
    expect(viewer).to_contain_text("a = 1")
    expect(viewer.get_file_header()).to_contain_text("+1")


@user_story("to verify that a commit-diff shows the commit's changes, not uncommitted edits")
def test_commit_diff_shows_committed_content_not_uncommitted(sculptor_instance_: SculptorInstance) -> None:
    """When a file has an uncommitted edit, the Commits panel's commit-scoped
    diff must show only the committed version's diff, not the uncommitted change.

    The cross-panel re-check (opening the same file's uncommitted diff from the
    Changes panel in the same tab bar) belonged to the retired shared tab surface;
    here the commit-scoped half is asserted against the Commits panel's own viewer.
    """
    page = sculptor_instance_.page
    commits_panel, first_commit = _open_commits_and_expand_first_commit(page, _COMMIT_THEN_EDIT_PROMPT)

    file_row = commits_panel.get_tree_rows(first_commit).filter(has_text="shared.py")
    expect(file_row).to_be_visible()
    file_row.click()

    # The commit added shared.py with "x = 1".  The diff should contain "x = 1".
    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("shared.py")
    expect(viewer).to_contain_text("x = 1")

    # The uncommitted edit changed it to "x = 2".  The commit diff should NOT
    # contain "x = 2" — that change hasn't been committed yet.
    expect(viewer).not_to_contain_text("x = 2")


@user_story("to not see a useless splitter when viewing a newly added file inside a commit diff")
def test_commit_diff_split_handle_hidden_for_added_file(sculptor_instance_: SculptorInstance) -> None:
    """An added file opened from the Commits panel never shows the split column
    handle, even with the split preference on — added files render unified
    because the "before" side is empty, so a draggable splitter is meaningless."""
    page = sculptor_instance_.page
    commits_panel, first_commit = _open_commits_and_expand_first_commit(page, _MULTI_FILE_COMMIT_PROMPT)

    # alpha.py is newly added in this commit (status "A").
    alpha_row = commits_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    viewer = commits_panel.get_diff_viewer()
    viewer.assert_diff_shows("alpha.py")
    expect(viewer).to_contain_text("a = 1")

    # Flip the view preference to split via the header menu. Added files always
    # render unified — there is no "before" side to show — so the split body
    # never mounts for alpha.py regardless of the preference. The flip is
    # therefore confirmed through the menu itself: the toggle offers
    # "Unified view" only while the split preference is active, which keeps the
    # handle assertion below from being trivially satisfied by a no-op click.
    viewer.toggle_view_option_via_menu("split_view")
    viewer.open_menu()
    expect(viewer.get_menu_option("split_view")).to_have_text("Unified view")
    page.keyboard.press("Escape")
    expect(viewer.get_menu_trigger()).to_have_attribute("aria-expanded", "false")

    # Even with the split preference active, the added file renders unified and
    # the handle must not appear — there is no left side to split.
    expect(viewer.get_unified_diff_views()).to_be_visible()
    expect(viewer.get_split_column_handle()).to_have_count(0)
