"""Integration tests for uncommitted changes shown in the Changes panel.

Tests verify that the Changes panel correctly shows only uncommitted changes
(HEAD->working tree), not the full history from the base branch. Tests that
involve commits use a feature branch so that the base branch (main) stays
behind, making committed vs uncommitted changes distinct.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Prompts that test committed-vs-uncommitted behavior start with
# `git checkout -b feature` so that commits land on the feature branch while
# `main` (the source_branch / diff base) stays at the initial commit.

_EDIT_AFTER_COMMIT_PROMPT = """\
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
        "file_path": "app.py",
        "content": "def main():\\n    print('hello')\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add app.py'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "app.py",
        "old_string": "print('hello')",
        "new_string": "print('goodbye')"
      }
    }
  ]
}`"""


@user_story("to see only uncommitted changes when clicking a file in the Changes panel")
def test_individual_file_diff_shows_only_uncommitted_changes(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Changes panel should show only uncommitted changes.

    After creating a feature branch, committing a file, then editing it again,
    the diff panel should show a modification diff (hello -> goodbye) -- not the
    entire file as newly added from the base branch.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_EDIT_AFTER_COMMIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("app.py")

    # The status indicator in the changes tree should show "M" (modified)
    status = changes_tree.get_row_status(tree_rows.first)
    expect(status).to_have_text("M")

    # Now click the file to open it in the diff panel
    tree_rows.first.click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    # Ensure unified mode via the toggle's data-state attribute
    diff_panel.ensure_unified_mode()

    # Wait for the diff file header to confirm the correct file is active
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("app.py")

    # The diff should show a modification: both 'hello' (removed) and 'goodbye'
    # (added) should be visible since it's a HEAD->working tree change.
    diff_view = diff_panel.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    expect(diff_view).to_contain_text("hello")
    expect(diff_view).to_contain_text("goodbye")


_COMMIT_THEN_EDIT_ONE_PROMPT = """\
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
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "alpha.py",
        "old_string": "a = 1",
        "new_string": "a = 999"
      }
    }
  ]
}`"""


def _enable_review_all_via_settings(page) -> None:  # noqa: ANN001
    """Enable the Review All setting via the Settings UI (idempotent)."""
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.enable_review_all()


@user_story("to see all branch files in Review All and uncommitted changes in individual file view")
def test_individual_diff_matches_review_all(sculptor_instance_: SculptorInstance) -> None:
    """Review All defaults to All scope (showing all branch changes), while
    individual file clicks from the Changes panel show uncommitted changes.

    After creating a feature branch, committing alpha.py and beta.py, then
    editing alpha.py: Review All (All scope) should show both alpha.py and
    beta.py, while clicking alpha.py individually shows the uncommitted edit.
    """
    page = sculptor_instance_.page

    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_ONE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # Only alpha.py should appear in the Uncommitted changes tree
    # (beta.py is committed and has no uncommitted changes)
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("alpha.py")

    # Open Review All — defaults to All scope, showing all branch changes
    file_browser = task_page.get_file_browser()
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()
    review_all_btn.click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    # Review All (All scope) should show both alpha.py and beta.py
    expect(diff_panel).to_contain_text("alpha.py")
    expect(diff_panel).to_contain_text("beta.py")

    # Now click alpha.py directly in the changes tree (Uncommitted scope)
    tree_rows.first.click()

    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("alpha.py")

    # Ensure unified mode.  We check here (after clicking the individual file)
    # rather than during Review All because Review All forces unified for
    # added ("A") files regardless of the stored preference, whereas the
    # individual file has status "M" and respects the stored preference.
    diff_panel.ensure_unified_mode()

    # The individual file diff should show the uncommitted change: a=1 -> a=999
    diff_view = diff_panel.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    expect(diff_view).to_contain_text("a = 1")
    expect(diff_view).to_contain_text("a = 999")


_COMMIT_ALL_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "done.py",
        "content": "x = 42\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add done.py'"
      }
    }
  ]
}`"""


@user_story("to see the changes panel clear after committing all changes")
def test_changes_panel_empty_after_commit(sculptor_instance_: SculptorInstance) -> None:
    """After committing all changes, the Changes panel should show no files."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_ALL_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()
    expect(changes_panel).to_contain_text("No changes")


_WRITE_AND_COMMIT_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "counter.py",
        "content": "count = 0\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add counter'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "counter.py",
        "old_string": "count = 0",
        "new_string": "count = 1"
      }
    }
  ]
}`"""

_COMMIT_AGAIN_PROMPT = """\
fake_claude:bash `{
  "command": "git add -A && git commit -m 'Increment counter'"
}`"""


@user_story("to see the changes panel update correctly after a second commit")
def test_changes_panel_updates_after_second_commit(sculptor_instance_: SculptorInstance) -> None:
    """The Changes panel should clear after committing the remaining changes.

    Sequence: write -> commit -> edit -> (file shows as M) -> commit again
    After the second commit, the Changes panel should be empty.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_AND_COMMIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("counter.py")

    # Now commit the remaining changes via a follow-up message
    send_chat_message(chat_panel=chat_panel, message=_COMMIT_AGAIN_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # After the second commit, Changes panel should be empty
    expect(tree_rows).to_have_count(0)


@user_story("to see correct line stats for uncommitted changes")
def test_diff_header_line_stats_reflect_uncommitted_only(sculptor_instance_: SculptorInstance) -> None:
    """Diff file header line stats should reflect only uncommitted changes.

    After creating a feature branch, committing a 5-line file, then modifying
    1 line, the header should show +1/-1 (the uncommitted edit), not +5/-0
    (the entire file as new from the base branch).
    """
    page = sculptor_instance_.page

    prompt = """\
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
        "file_path": "lines.py",
        "content": "line1 = 1\\nline2 = 2\\nline3 = 3\\nline4 = 4\\nline5 = 5\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add lines.py'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "lines.py",
        "old_string": "line3 = 3",
        "new_string": "line3 = 333"
      }
    }
  ]
}`"""
    task_page = start_task_and_wait_for_ready(page, prompt=prompt)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    tree_rows.first.click()

    diff_panel = task_page.get_diff_panel()
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_be_visible()
    expect(diff_header).to_contain_text("lines.py")

    # The uncommitted change is 1 line modified (1 added, 1 removed).
    # The header should show +1 (not +5).
    expect(diff_header).to_contain_text("+1")
    expect(diff_header).not_to_contain_text("+5")


_NEW_FILE_WITH_DELETED_FILE_MODE_CONTENT_PROMPT = """\
fake_claude:write_file `{
  "file_path": "tricky.txt",
  "content": "This file talks about deleted file mode in git diffs.\\n"
}`"""

_EDIT_FILE_TO_ADD_DELETED_FILE_MODE_CONTENT_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "notes.txt",
        "content": "Some initial content.\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add notes.txt'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "notes.txt",
        "old_string": "Some initial content.",
        "new_string": "This line mentions deleted file mode for documentation."
      }
    }
  ]
}`"""


@user_story("to see correct status for files whose content contains 'deleted file mode'")
def test_file_containing_deleted_file_mode_text_not_shown_as_deleted(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Files whose content contains 'deleted file mode' should not be marked as deleted.

    The determineFileStatus function must not match diff metadata patterns
    against file content. A new file with 'deleted file mode' in its body
    should show status 'A' (added), and an edited file with the same text
    should show status 'M' (modified).
    """
    page = sculptor_instance_.page

    # --- Scenario 1: new file whose content contains "deleted file mode" ---
    task_page = start_task_and_wait_for_ready(page, prompt=_NEW_FILE_WITH_DELETED_FILE_MODE_CONTENT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("tricky.txt")

    # The file is newly added — status must be "A", not "D"
    status = changes_tree.get_row_status(tree_rows.first)
    expect(status).to_have_text("A")

    # --- Scenario 2: edited file whose new content contains "deleted file mode" ---
    send_chat_message(
        chat_panel=chat_panel,
        message=_EDIT_FILE_TO_ADD_DELETED_FILE_MODE_CONTENT_PROMPT,
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The `git add -A && git commit` in the second prompt commits everything
    # (including tricky.txt from the first prompt). Only notes.txt remains
    # uncommitted after being edited — it should show as "M", not "D".
    notes_row = changes_tree.get_tree_rows().filter(has_text="notes.txt")
    expect(notes_row).to_be_visible()
    notes_status = changes_tree.get_row_status(notes_row)
    expect(notes_status).to_have_text("M")
