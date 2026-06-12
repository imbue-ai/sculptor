"""Integration tests for history panel diff interactions.

Tests verify that clicking files in the history panel correctly opens
commit-scoped diffs, and that commit-diff tabs coexist properly with
regular diff tabs in the tab bar.
"""

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.history_panel import PlaywrightHistoryPanelElement
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Creates a branch with a single commit that touches TWO files.
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

# Creates a branch, commits a file, then leaves an uncommitted edit to the same file.
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

# Creates two commits that both modify the SAME file (shared.py).
# Commit 1 adds the file, commit 2 modifies it.
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

# Creates two separate commits, each touching a different file.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_history_and_expand_first_commit(
    task_page: PlaywrightTaskPage,
) -> tuple[PlaywrightHistoryPanelElement, Locator]:
    """Open the History panel and expand the first (most recent) commit.

    Returns a tuple of (history_panel_pom, commit_entry).
    """
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    first_commit = history_panel.get_commit_entries().first
    history_panel.get_commit_message(first_commit).click()

    return history_panel, first_commit


# ---------------------------------------------------------------------------
# Bug 1: clicking a file in a multi-file commit crashes
# ---------------------------------------------------------------------------


@user_story("to view a single file's diff from a multi-file commit without the diff viewer crashing")
def test_click_file_in_multi_file_commit(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a file inside a commit that has 2+ changed files should open
    that file's commit-scoped diff without crashing."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_MULTI_FILE_COMMIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    history_panel, first_commit = _open_history_and_expand_first_commit(task_page)

    # The commit has two files: alpha.py and beta.py.  Click alpha.py.
    file_rows = history_panel.get_tree_rows(first_commit)
    expect(file_rows).to_have_count(2)

    alpha_row = history_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    # A diff tab should appear with the commit-scoped label.
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel.get_tabs().first).to_be_visible()

    # The diff panel should show diff content — NOT an error or blank screen.
    expect(diff_panel).to_be_visible()
    # The rendered diff should contain the file's actual content.
    expect(diff_panel).to_contain_text("a = 1")


# ---------------------------------------------------------------------------
# Bug 2: commit-diff tab not re-selectable after opening same file from Changes
# ---------------------------------------------------------------------------


@user_story("to switch between a commit-diff tab and an uncommitted-diff tab for the same file")
def test_commit_diff_tab_selectable_alongside_regular_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After opening a file from the history panel (commit-diff tab) and then
    opening the same file from the Changes panel (regular tab), both tabs
    should remain independently selectable."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Step 1: Open the history panel and click shared.py in the commit.
    history_panel, first_commit = _open_history_and_expand_first_commit(task_page)

    file_row = history_panel.get_tree_rows(first_commit).filter(has_text="shared.py")
    expect(file_row).to_be_visible()
    file_row.click()

    # Verify the commit-diff tab appeared with the hash suffix.
    diff_panel = task_page.get_diff_panel()
    diff_tabs = diff_panel.get_tabs()
    commit_tab = diff_tabs.filter(has_text="shared.py (")
    expect(commit_tab).to_be_visible()

    # Step 2: Switch to the Changes tab and click shared.py (uncommitted edit).
    task_page.activate_changes_panel()
    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    changes_tree = changes_panel.get_changes_tree()
    changes_file = changes_tree.get_tree_rows().filter(has_text="shared.py")
    expect(changes_file).to_be_visible()
    changes_file.click()

    # Now there should be two tabs: "shared.py" and "shared.py (<hash>)".
    regular_tab = diff_tabs.filter(has_text="shared.py").filter(has_not_text="(")
    expect(regular_tab).to_be_visible()
    expect(commit_tab).to_be_visible()

    # Step 3: Click the commit-diff tab to switch back to it.
    commit_tab.click()

    # The commit-diff tab should be the *active* tab (aria-selected="true").
    expect(commit_tab).to_have_attribute("aria-selected", "true")


# ---------------------------------------------------------------------------
# Additional bug exploration: clicking files from two different commits
# ---------------------------------------------------------------------------


@user_story("to open diffs from two different commits and switch between them")
def test_open_files_from_different_commits(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Opening files from two different commits should create two separate
    commit-diff tabs that are independently viewable."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_TWO_SINGLE_FILE_COMMITS_PROMPT, wait_for_agent_to_finish=False
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    commits = history_panel.get_commit_entries()
    # The mock repo has 2 pre-existing commits on the testing branch (app.py,
    # stuff.txt) plus the 2 agent-created commits = 4 total since main.
    expect(commits).to_have_count(4)

    # Expand and click the file in the first (most recent) commit: "Add second.py"
    first_commit = commits.nth(0)
    history_panel.get_commit_message(first_commit).click()
    second_py_row = history_panel.get_tree_rows(first_commit).filter(has_text="second.py")
    expect(second_py_row).to_be_visible()
    second_py_row.click()

    diff_panel = task_page.get_diff_panel()
    diff_tabs = diff_panel.get_tabs()
    second_tab = diff_tabs.filter(has_text="second.py (")
    expect(second_tab).to_be_visible()

    # Expand and click the file in the second commit: "Add first.py"
    second_commit = commits.nth(1)
    history_panel.get_commit_message(second_commit).click()
    first_py_row = history_panel.get_tree_rows(second_commit).filter(has_text="first.py")
    expect(first_py_row).to_be_visible()
    first_py_row.click()

    first_tab = diff_tabs.filter(has_text="first.py (")
    expect(first_tab).to_be_visible()

    # Both tabs should exist
    expect(second_tab).to_be_visible()
    expect(first_tab).to_be_visible()

    # Click the second.py commit-diff tab to go back to it.
    second_tab.click()
    expect(second_tab).to_have_attribute("aria-selected", "true")

    # Click the first.py commit-diff tab.
    first_tab.click()
    expect(first_tab).to_have_attribute("aria-selected", "true")


# ---------------------------------------------------------------------------
# Additional: closing a commit-diff tab should not affect regular tabs
# ---------------------------------------------------------------------------


@user_story("to close a commit-diff tab without losing the regular diff tab for the same file")
def test_close_commit_diff_tab_keeps_regular_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Closing a commit-diff tab should leave the regular diff tab for the
    same file untouched."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open uncommitted diff first via Changes tab.
    task_page.activate_changes_panel()
    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    changes_tree = changes_panel.get_changes_tree()
    changes_file = changes_tree.get_tree_rows().filter(has_text="shared.py")
    expect(changes_file).to_be_visible()
    changes_file.click()

    diff_panel = task_page.get_diff_panel()
    diff_tabs = diff_panel.get_tabs()
    regular_tab = diff_tabs.filter(has_text="shared.py").filter(has_not_text="(")
    expect(regular_tab).to_be_visible()

    # Now open the commit-diff tab via History tab.
    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    first_commit = history_panel.get_commit_entries().first
    history_panel.get_commit_message(first_commit).click()

    file_row = history_panel.get_tree_rows(first_commit).filter(has_text="shared.py")
    expect(file_row).to_be_visible()
    file_row.click()

    commit_tab = diff_tabs.filter(has_text="shared.py (")
    expect(commit_tab).to_be_visible()

    # Middle-click the commit-diff tab to close it.
    commit_tab.click(button="middle")

    # The commit-diff tab should be gone, but the regular tab should remain.
    expect(commit_tab).not_to_be_visible()
    expect(regular_tab).to_be_visible()

    # And the regular tab's diff should be viewable.
    expect(diff_panel).to_contain_text("x = 2")


# ---------------------------------------------------------------------------
# Edge case: same file modified in two commits shows correct diff per tab
# ---------------------------------------------------------------------------


@user_story("to view the correct diff content when the same file is modified across two commits")
def test_same_file_two_commits_shows_correct_content(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the same file is changed in two commits, each commit-diff tab
    should show that commit's diff — not the other commit's diff."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_SAME_FILE_TWO_COMMITS_PROMPT, wait_for_agent_to_finish=False
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    task_page.activate_history_panel()
    history_panel = task_page.get_history_panel()
    expect(history_panel).to_be_visible()

    commits = history_panel.get_commit_entries()
    # The mock repo has 2 pre-existing commits on the testing branch (app.py,
    # stuff.txt) plus the 2 agent-created commits = 4 total since main.
    expect(commits).to_have_count(4)

    # Commit 0 (most recent): "Update shared.py v2" — modifies shared.py
    # Commit 1 (older): "Add shared.py v1" — adds shared.py
    v2_commit = commits.nth(0)
    v1_commit = commits.nth(1)

    # Open shared.py from the v2 commit (modification diff).
    history_panel.get_commit_message(v2_commit).click()
    v2_file_row = history_panel.get_tree_rows(v2_commit).filter(has_text="shared.py")
    expect(v2_file_row).to_be_visible()
    v2_file_row.click()

    diff_panel = task_page.get_diff_panel()
    diff_tabs = diff_panel.get_tabs()

    # The v2 commit modified the file: should show version_two = 2
    v2_tab = diff_tabs.filter(has_text="shared.py (")
    expect(v2_tab).to_be_visible()
    expect(diff_panel).to_contain_text("version_two")

    # Open shared.py from the v1 commit (addition diff).
    history_panel.get_commit_message(v1_commit).click()
    v1_file_row = history_panel.get_tree_rows(v1_commit).filter(has_text="shared.py")
    expect(v1_file_row).to_be_visible()
    v1_file_row.click()

    # Now there should be two commit-diff tabs for shared.py (different hashes).
    commit_tabs = diff_tabs.filter(has_text="shared.py (")
    expect(commit_tabs).to_have_count(2)

    # The v1 commit added the file: should show version_one = 1
    expect(diff_panel).to_contain_text("version_one")

    # Switch back to the v2 tab and verify it shows the modification diff.
    # Identify v2 tab by its commit message text in the label.
    # Both tabs have "shared.py (HASH)" labels. We need to click the first one
    # (v2 was opened first, so it's first in the tab bar).
    commit_tabs.first.click()
    expect(commit_tabs.first).to_have_attribute("aria-selected", "true")
    expect(diff_panel).to_contain_text("version_two")


# ---------------------------------------------------------------------------
# Edge case: switching between files within a single multi-file commit
# ---------------------------------------------------------------------------


@user_story("to switch between different file diffs within the same commit")
def test_switch_files_within_same_commit(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Opening two files from the same commit should create two tabs, and
    switching between them should show each file's individual diff."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_MULTI_FILE_COMMIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    history_panel, first_commit = _open_history_and_expand_first_commit(task_page)

    # Open alpha.py
    alpha_row = history_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    diff_panel = task_page.get_diff_panel()
    diff_tabs = diff_panel.get_tabs()

    alpha_tab = diff_tabs.filter(has_text="alpha.py (")
    expect(alpha_tab).to_be_visible()
    expect(diff_panel).to_contain_text("a = 1")

    # Open beta.py from the same commit
    beta_row = history_panel.get_tree_rows(first_commit).filter(has_text="beta.py")
    expect(beta_row).to_be_visible()
    beta_row.click()

    beta_tab = diff_tabs.filter(has_text="beta.py (")
    expect(beta_tab).to_be_visible()
    expect(diff_panel).to_contain_text("b = 2")

    # Switch back to alpha.py tab — should show alpha's content, not beta's
    alpha_tab.click()
    expect(alpha_tab).to_have_attribute("aria-selected", "true")
    expect(diff_panel).to_contain_text("a = 1")


# ---------------------------------------------------------------------------
# Bug 3: DiffFileHeader shows +0 -0 for commit-diff tabs
# ---------------------------------------------------------------------------


@user_story("to see correct line count stats in the file header for a commit-scoped diff")
def test_commit_diff_file_header_shows_line_counts(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The file header above a commit-scoped diff should display the actual
    added/removed line counts from the commit, not +0 -0."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_MULTI_FILE_COMMIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    history_panel, first_commit = _open_history_and_expand_first_commit(task_page)

    # Click alpha.py — a file with 1 added line ("a = 1\n").
    alpha_row = history_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    # Wait for the diff to load.
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_contain_text("a = 1")

    # The file header should show +1 (1 added line), not +0.
    # Bug: DiffPanel.tsx passes addedLines={0} and removedLines={0} to
    # DiffFileHeader for commit-diff tabs, so the header always shows +0 -0.
    expect(diff_panel.get_file_header()).to_contain_text("+1")


# ---------------------------------------------------------------------------
# Edge case: commit-diff tab shows only its commit's content
# ---------------------------------------------------------------------------


@user_story("to verify that a commit-diff tab shows the commit's changes, not uncommitted edits")
def test_commit_diff_shows_committed_content_not_uncommitted(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When viewing a commit-diff tab alongside an uncommitted change to the
    same file, the commit-diff tab must show only the committed version's
    diff, not any uncommitted changes."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    # Open the commit-diff tab via History panel.
    history_panel, first_commit = _open_history_and_expand_first_commit(task_page)
    file_row = history_panel.get_tree_rows(first_commit).filter(has_text="shared.py")
    expect(file_row).to_be_visible()
    file_row.click()

    diff_panel = task_page.get_diff_panel()
    diff_tabs = diff_panel.get_tabs()

    # The commit added shared.py with "x = 1".  The diff should contain "x = 1".
    commit_tab = diff_tabs.filter(has_text="shared.py (")
    expect(commit_tab).to_be_visible()
    expect(diff_panel).to_contain_text("x = 1")

    # The uncommitted edit changed it to "x = 2".  The commit diff should
    # NOT contain "x = 2" — that change hasn't been committed yet.
    expect(diff_panel).not_to_contain_text("x = 2")

    # Now open the regular (uncommitted) diff tab via Changes tab.
    task_page.activate_changes_panel()
    changes_panel = task_page.get_changes_panel()
    changes_tree = changes_panel.get_changes_tree()
    changes_file = changes_tree.get_tree_rows().filter(has_text="shared.py")
    expect(changes_file).to_be_visible()
    changes_file.click()

    # The regular tab should show the uncommitted change "x = 2".
    regular_tab = diff_tabs.filter(has_text="shared.py").filter(has_not_text="(")
    expect(regular_tab).to_be_visible()
    expect(diff_panel).to_contain_text("x = 2")

    # Switch back to the commit-diff tab.
    commit_tab.click()
    expect(commit_tab).to_have_attribute("aria-selected", "true")

    # After switching back, should show committed content only.
    expect(diff_panel).to_contain_text("x = 1")
    expect(diff_panel).not_to_contain_text("x = 2")


# ---------------------------------------------------------------------------
# Bug 4: split-view handle rendered for an added file inside a commit diff
# ---------------------------------------------------------------------------


@user_story("to not see a useless splitter when viewing a newly added file inside a commit diff")
def test_commit_diff_split_handle_hidden_for_added_file(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Opening an added file from the commits tab in split view should not
    render the split column handle — the "before" side is empty, so a
    draggable splitter is meaningless.

    DiffPanel applies `effectiveViewType = unified` for A/D files in the
    normal diff path, but the commit-diff path used raw `viewType`, letting
    the handle render on an add.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_MULTI_FILE_COMMIT_PROMPT, wait_for_agent_to_finish=False)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

    history_panel, first_commit = _open_history_and_expand_first_commit(task_page)

    # alpha.py is newly added in this commit (status "A").
    alpha_row = history_panel.get_tree_rows(first_commit).filter(has_text="alpha.py")
    expect(alpha_row).to_be_visible()
    alpha_row.click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_contain_text("a = 1")

    # Switch to split view.
    diff_panel.ensure_split_mode()

    # Even in split mode, the handle must not appear for an added file —
    # there is no left side to split.
    expect(diff_panel.get_split_column_handle()).to_have_count(0)
