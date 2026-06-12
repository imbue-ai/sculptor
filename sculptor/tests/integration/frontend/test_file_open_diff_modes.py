"""Integration tests for the different ways files can be opened and the diffs shown.

Covers three file-open modes from the File Browser:
1. **Browse tab** — opens a read-only file view (no diff).
2. **Changes tab, Uncommitted scope** — opens a diff of HEAD vs working tree.
3. **Changes tab, All scope** — opens a diff of merge-base(target) vs working tree.

The test setup creates a feature branch with a committed file and an additional
uncommitted edit so that committed-vs-uncommitted changes are distinct.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Setup: create a feature branch, write "hello" to myapp.py and commit, then
# edit it to "goodbye" without committing.
#
# Expected diffs:
#   Uncommitted (HEAD -> working tree):  "hello" -> "goodbye"
#   All (merge-base -> working tree):    entire file "goodbye" is new (addition)
#   Browse:                              plain file view, no diff
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
        "file_path": "myapp.py",
        "content": "print('hello')\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add myapp.py'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "myapp.py",
        "old_string": "print('hello')",
        "new_string": "print('goodbye')"
      }
    }
  ]
}`"""


@user_story("to see plain file contents when clicking a file in the Browse tab")
def test_browse_tab_opens_file_view(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Browse tab should open a read-only file preview,
    not a diff view."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    # Switch to Browse tab
    browse_tab = file_browser.get_tab_all()
    expect(browse_tab).to_be_visible()
    browse_tab.click()

    # Click myapp.py in the file tree
    tree_rows = file_browser.get_tree_rows()
    app_row = tree_rows.filter(has_text="myapp.py")
    expect(app_row).to_be_visible()
    app_row.click()

    # Should open the read-only preview (not a diff view)
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    preview = diff_panel.get_read_only_preview()
    expect(preview).to_be_visible()

    # The preview should show the current working tree content ("goodbye")
    expect(preview).to_contain_text("goodbye")


@user_story("to see uncommitted diff when clicking a file in Uncommitted scope")
def test_uncommitted_scope_shows_head_vs_working_tree_diff(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Changes tab with Uncommitted scope should show
    only the HEAD-to-working-tree diff (hello -> goodbye)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    # Switch to Changes tab
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    # Ensure Uncommitted scope is selected (default)
    changes_panel = task_page.get_changes_panel()
    scope_picker = changes_panel.get_scope_picker()
    expect(scope_picker).to_be_visible()
    changes_panel.get_scope_uncommitted().click()

    # Click myapp.py
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("myapp.py")
    tree_rows.first.click()

    # Verify diff panel shows the uncommitted change
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    diff_panel.ensure_unified_mode()

    diff_view = diff_panel.get_unified_diff_views()
    expect(diff_view).to_be_visible()

    # Uncommitted diff: "hello" removed, "goodbye" added
    expect(diff_view).to_contain_text("hello")
    expect(diff_view).to_contain_text("goodbye")

    # The diff header should show a modification (+1 -1), not a full addition
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("myapp.py")
    expect(diff_header).to_contain_text("+1")
    expect(diff_header).to_contain_text("-1")


@user_story("to see full branch diff when clicking a file in All scope")
def test_all_scope_shows_merge_base_vs_working_tree_diff(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Changes tab with All scope should show the
    merge-base-to-working-tree diff (the entire file as a new addition
    with the current working tree content)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    # Switch to Changes tab
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    # Switch to All scope
    changes_panel = task_page.get_changes_panel()
    changes_panel.get_scope_all().click()

    # Click myapp.py in the All scope view
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    app_row = tree_rows.filter(has_text="myapp.py")
    expect(app_row).to_be_visible()
    app_row.click()

    # Verify diff panel shows the target-branch diff
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    diff_panel.ensure_unified_mode()

    diff_view = diff_panel.get_unified_diff_views()
    expect(diff_view).to_be_visible()

    # All diff (merge-base -> working tree): should show the current content
    # "goodbye" as an addition. Should NOT show "hello" since the working tree
    # has already been edited.
    expect(diff_view).to_contain_text("goodbye")
    expect(diff_view).not_to_contain_text("hello")


@user_story("to see both uncommitted and all-scope diffs for the same file in separate tabs")
def test_same_file_opens_separate_tabs_per_scope(sculptor_instance_: SculptorInstance) -> None:
    """Opening the same file from Uncommitted and All scopes should create two
    separate diff tabs, each showing the appropriate diff."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_THEN_EDIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    # Switch to Changes tab
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    changes_panel = task_page.get_changes_panel()

    # First: open from Uncommitted scope
    changes_panel.get_scope_uncommitted().click()
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    tree_rows.filter(has_text="myapp.py").click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    # Second: switch to All scope and click the file again
    changes_panel.get_scope_all().click()
    # Re-query tree rows since the scope change may re-render
    changes_tree = changes_panel.get_changes_tree()
    tree_rows = changes_tree.get_tree_rows()
    tree_rows.filter(has_text="myapp.py").click()

    # Should now have two separate tabs for myapp.py
    app_tabs = diff_panel.get_tabs().filter(has_text="myapp.py")
    expect(app_tabs).to_have_count(2)


# Setup: multi-line file with a unique marker on line 11. Line 7 is edited so
# the hunk covers lines 4–10 (3 context lines on each side). Lines 11+ lie
# outside the hunk and are rendered as Pierre expansion lines.  When the
# frontend strips the trailing '\n' from the diff string, Pierre concatenates
# the last hunk line (line 10) directly with expansion line 11, causing Shiki
# to treat them as a single line.  Every subsequent line number is then off
# by one.
_LINE_NUMBER_REGRESSION_PROMPT = """\
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
        "file_path": "multiline.py",
        "content": "line_01\\nline_02\\nline_03\\nline_04\\nline_05\\nline_06\\nline_07\\nline_08\\nline_09\\nline_10\\nafter_hunk_line_eleven\\nline_12\\nline_13\\nline_14\\nline_15\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add multiline.py'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "multiline.py",
        "old_string": "line_07",
        "new_string": "line_07_edited"
      }
    }
  ]
}`"""


@user_story("to see correct line numbers for expansion lines beyond the last diff hunk")
def test_diff_view_shows_correct_line_numbers(sculptor_instance_: SculptorInstance) -> None:
    """Lines that appear after the last hunk's 3-context-line window are
    rendered by Pierre as expansion lines drawn from the full file content.
    The frontend used to strip the trailing newline from the diff string, which
    caused Pierre to concatenate the last hunk line with the first expansion
    line.  Shiki then treated the two as one line, shifting all subsequent line
    numbers by one.  After the fix, every line must carry the correct number."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_LINE_NUMBER_REGRESSION_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    changes_panel = task_page.get_changes_panel()
    changes_panel.get_scope_uncommitted().click()

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    tree_rows.filter(has_text="multiline.py").click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    diff_panel.ensure_unified_mode()

    diff_view = diff_panel.get_unified_diff_views()
    expect(diff_view).to_be_visible()

    # "after_hunk_line_eleven" is on file line 11, just outside the hunk's
    # 3-line context window (hunk covers lines 4–10).  When the frontend strips
    # the trailing '\n' from the diff string, Pierre's processLines concatenates
    # line 10 (the last hunk line) with line 11 during Shiki tokenisation,
    # causing them to render as a single merged line.
    #
    # Pierre renders inside a shadow DOM (<diffs-container>), so we must pierce
    # it with page.evaluate (data-line is a Pierre attribute with no Playwright
    # API equivalent — read-only DOM inspection, not state manipulation).
    # Wait for Pierre's shadow DOM to render line divs.  The container may be
    # visible before the shadow DOM content finishes rendering (Shiki
    # tokenisation is async), so we poll until at least one div[data-line]
    # appears inside the shadow root.
    testid = ElementIDs.DIFF_VIEW_UNIFIED
    page.wait_for_function(
        """(testid) => {
            const dv = document.querySelector(`[data-testid="${testid}"]`);
            const shadow = dv?.querySelector("diffs-container")?.shadowRoot;
            return shadow?.querySelectorAll("div[data-line]").length > 0;
        }""",
        arg=testid,
    )
    result = page.evaluate(
        """(testid) => {
            const diffView = document.querySelector(`[data-testid="${testid}"]`);
            if (!diffView) return { error: "no-diff-view" };
            const shadow = diffView.querySelector("diffs-container")?.shadowRoot;
            if (!shadow) return { error: "no-shadow-root" };
            const divs = shadow.querySelectorAll("div[data-line]");
            for (const div of divs) {
                if (div.textContent.includes("line_10")) {
                    return {
                        dataLine: div.getAttribute("data-line"),
                        merged: div.textContent.includes("after_hunk_line_eleven"),
                        text: div.textContent.substring(0, 200),
                    };
                }
            }
            return { error: "line_10-not-found", divCount: divs.length };
        }""",
        testid,
    )
    assert isinstance(result, dict) and "error" not in result, f"Could not locate line_10 in the diff view: {result}"
    assert not result["merged"], (
        f"Last hunk line (data-line={result['dataLine']}) merged with expansion line 11: {result['text']!r};"
        + " the trailing newline was likely stripped from the diff string."
    )


# Setup: committed-only file. Create feature branch, write and commit a file,
# no further edits. This file only appears in the All scope (not Uncommitted).
_COMMITTED_ONLY_PROMPT = """\
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
        "file_path": "committed.py",
        "content": "x = 42\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add committed.py'"
      }
    }
  ]
}`"""


@user_story("to see committed-only files in All scope but not in Uncommitted scope")
def test_committed_file_visible_in_all_scope_only(sculptor_instance_: SculptorInstance) -> None:
    """A file that has been committed with no further edits should appear in the
    All scope (it's new relative to the target branch) but not in the
    Uncommitted scope (no working tree changes)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMITTED_ONLY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()

    # Switch to Changes tab
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    # In Uncommitted scope, there should be no changes
    changes_panel = task_page.get_changes_panel()
    changes_panel.get_scope_uncommitted().click()
    expect(changes_panel).to_contain_text("No changes")

    # Switch to All scope — committed.py should appear
    changes_panel.get_scope_all().click()
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    committed_row = tree_rows.filter(has_text="committed.py")
    expect(committed_row).to_be_visible()

    # Click it to verify the diff shows the file as a full addition
    committed_row.click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    diff_panel.ensure_unified_mode()

    diff_view = diff_panel.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    expect(diff_view).to_contain_text("x = 42")
