"""Integration tests for the File Browser panel and Diff Panel."""

import re
from pathlib import Path

from playwright.sync_api import ConsoleMessage
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.diff_panel import get_diff_panel_from_page
from sculptor.testing.elements.file_browser import get_file_browser_panel
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _enable_review_all_via_settings(page: Page) -> None:
    """Enable the Review All experimental setting via the Settings UI."""
    settings_page = navigate_to_settings_page(page=page)
    experimental_nav = settings_page.get_by_test_id(ElementIDs.SETTINGS_NAV_EXPERIMENTAL)
    expect(experimental_nav).to_be_visible()
    experimental_nav.click()
    toggle = settings_page.get_by_test_id(ElementIDs.SETTINGS_ENABLE_REVIEW_ALL_TOGGLE)
    expect(toggle).to_be_visible()
    if toggle.get_attribute("data-state") != "checked":
        toggle.click()


WRITE_FILES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "src/App.tsx",
        "content": "import React from 'react';\\nexport const App = () => <div>Hello</div>;\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "src/components/Header.tsx",
        "content": "import React from 'react';\\nexport const Header = () => <header>Header</header>;\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "README.md",
        "content": "# Test Project\\n\\nA test project for integration testing.\\n"
      }
    }
  ]
}`"""


def _start_task_with_files(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    """Start a task that creates three files and wait for completion."""
    task_page = start_task_and_wait_for_ready(
        sculptor_instance.page,
        prompt=WRITE_FILES_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    return task_page


def _open_file_in_diff(page: Page, file_text: str) -> None:
    """Click a file row in the tree to open it in the diff panel."""
    file_browser = get_file_browser_panel(page)
    row = file_browser.get_tree_rows().filter(has_text=file_text)
    row.first.click()
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()


def _open_file_in_changes_diff(page: Page, file_text: str) -> None:
    """Open a file from the Changes tab so it opens as a diff (not a read-only preview).

    The Browse tab opens files via ``openFileViewTab`` which renders a
    ``ReadOnlyPreview``.  The Changes tab opens files via ``openDiffTab``
    which renders ``PierreDiffView`` with DIFF_VIEW_UNIFIED/SPLIT test IDs.
    """
    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()
    row = changes_tree.get_tree_rows().filter(has_text=file_text)
    expect(row.first).to_be_visible()
    row.first.click()

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()


def _ensure_render_mode(page: Page, mode: str) -> None:
    """Ensure the read-only preview's render-mode toggle is in ``mode``
    (``"rendered"`` or ``"source"``).

    The default mode is persisted globally to localStorage, so a previous
    test in the same browser context could leave it in either state. This
    helper inspects the toggle's ``data-state`` and only clicks if needed,
    then verifies the post-click state.
    """
    diff_panel = get_diff_panel_from_page(page)
    toggle = diff_panel.get_render_toggle()
    expect(toggle).to_be_visible()
    if toggle.get_attribute("data-state") != mode:
        toggle.click()
    expect(toggle).to_have_attribute("data-state", mode)


def _ensure_folder_expanded(page: Page, folder_text: str) -> None:
    """Expand a folder if not already expanded.

    During agent execution, the auto-expand effect may have already expanded
    ancestor folders of files the agent operates on. Blindly clicking the
    folder row would collapse it in that case. This helper checks the
    ``aria-expanded`` attribute first and only clicks when needed.
    """
    file_browser = get_file_browser_panel(page)
    folder_row = file_browser.get_tree_rows().filter(has_text=folder_text).first
    expect(folder_row).to_be_visible()
    if folder_row.get_attribute("aria-expanded") != "true":
        folder_row.click()


@user_story("to browse files the agent has created")
def test_file_browser_shows_tree_after_agent_writes(sculptor_instance_: SculptorInstance) -> None:
    """File browser shows the file tree after the agent creates files."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # File browser panel should be visible (it's the default active panel)
    file_browser = get_file_browser_panel(page)
    expect(file_browser).to_be_visible()

    # The file tree should render with tree rows
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # We should see tree rows for the files/folders
    tree_rows = file_tree.get_tree_rows()
    expect(tree_rows.first).to_be_visible()

    # README.md should be visible (root-level file)
    expect(file_tree).to_contain_text("README")


@user_story("to see which files have been changed")
def test_file_tree_shows_status_indicators(sculptor_instance_: SculptorInstance) -> None:
    """File tree rows show status letter indicators for changed files."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Status indicators (A for added) should be visible on file rows
    status_indicators = file_browser.get_status_indicators()
    expect(status_indicators.first).to_be_visible()


@user_story("to filter files by changes only")
def test_filter_tabs_switch_between_all_and_changes(sculptor_instance_: SculptorInstance) -> None:
    """Filter tabs switch between All (tree) and Changes (flat list) views."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    expect(file_browser).to_be_visible()

    # All tab should be active by default
    all_tab = file_browser.get_tab_all()
    changes_tab = file_browser.get_tab_changes()
    expect(all_tab).to_be_visible()
    expect(changes_tab).to_be_visible()

    # Click Changes tab
    changes_tab.click()

    # Changes tree should appear
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # Click All tab to go back
    all_tab.click()

    # File tree should be back
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()


@user_story("to quickly find a file by name")
def test_file_search(sculptor_instance_: SculptorInstance) -> None:
    """File search filters the tree to matching files and closes cleanly."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    expect(file_browser).to_be_visible()

    # File tree should be visible before search
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Click search button
    search_btn = file_browser.get_search_button()
    search_btn.click()

    # Search input should appear
    search_input = file_browser.get_search_input()
    expect(search_input).to_be_visible()

    # File tree should still be visible during search
    expect(file_tree).to_be_visible()

    # Tab buttons should still be visible
    all_tab = file_browser.get_tab_all()
    expect(all_tab).to_be_visible()

    # Type a query
    search_input.fill("Header")

    # File tree should still be visible with filtered results
    expect(file_tree).to_be_visible()

    # Close search
    close_btn = file_browser.get_search_close()
    close_btn.click()

    # File tree should still be visible
    expect(file_tree).to_be_visible()


@user_story("to view a diff for a file")
def test_click_file_opens_diff_panel(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the tree opens the diff panel with that file's diff."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Click on README.md (a root-level file that should be immediately visible)
    readme_row = file_browser.get_tree_rows().filter(has_text="README")
    readme_row.first.click()

    # Diff panel should appear
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Tab bar should have a tab for the file
    diff_tabs = diff_panel.get_tabs()
    expect(diff_tabs.first).to_be_visible()

    # File header should show the path
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_be_visible()
    expect(diff_header).to_contain_text("README")


@user_story("to manage multiple open files")
def test_multiple_tabs_and_close(sculptor_instance_: SculptorInstance) -> None:
    """Opening multiple files creates tabs; closing a tab removes it."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Click README.md to open first tab
    readme_row = file_browser.get_tree_rows().filter(has_text="README")
    readme_row.first.click()

    diff_panel = get_diff_panel_from_page(page)
    diff_tabs = diff_panel.get_tabs()
    expect(diff_tabs).to_have_count(1)

    # Expand src/ folder (may already be expanded from auto-expand), then click App.tsx
    _ensure_folder_expanded(page, "src")
    app_row = file_browser.get_tree_rows().filter(has_text="App.tsx")
    app_row.first.click()

    # Should now have 2 tabs
    expect(diff_tabs).to_have_count(2)

    # Close the second tab (App.tsx) by clicking its close button within the tab
    second_tab = diff_tabs.nth(1)
    second_tab.hover()
    close_button = second_tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    # Should be back to 1 tab
    expect(diff_tabs).to_have_count(1)


@user_story("to have a clean view when no files are open")
def test_closing_last_tab_keeps_diff_panel_open_with_placeholder(sculptor_instance_: SculptorInstance) -> None:
    """Closing the last diff tab leaves the panel open and shows a placeholder.

    Mirrors how the other docked panels behave — closing the last item does
    not collapse the panel column.  Use the dedicated close-panel button to
    actually hide the panel.
    """
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    readme_row = file_browser.get_tree_rows().filter(has_text="README")
    readme_row.first.click()

    # Diff panel should be visible
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Close the tab by clicking close button within the tab element
    diff_tabs = diff_panel.get_tabs()
    diff_tabs.first.hover()
    close_button = diff_tabs.first.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
    close_button.click()

    # The panel stays visible — no tabs, but the empty-state placeholder is shown.
    expect(diff_panel).to_be_visible()
    expect(diff_tabs).to_have_count(0)
    expect(diff_panel).to_contain_text("Open a file to view it")


@user_story("to see diffs update when the agent modifies files")
def test_diff_updates_on_agent_edit(sculptor_instance_: SculptorInstance) -> None:
    """Diff content updates when the agent modifies an already-opened file."""
    task_page = _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open README.md diff
    file_browser = get_file_browser_panel(page)
    readme_row = file_browser.get_tree_rows().filter(has_text="README")
    readme_row.first.click()

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Now have the agent edit the file
    chat_panel = task_page.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:edit_file `{
  "file_path": "README.md",
  "old_string": "# Test Project",
  "new_string": "# Updated Test Project\\n\\nWith extra content."
}`""",
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The diff panel should still be showing README.md
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("README")


@user_story("to see the file browser when the agent hasn't changed any files yet")
def test_file_browser_shows_tree_before_agent_changes(sculptor_instance_: SculptorInstance) -> None:
    """File browser shows the file tree (from existing repo files) before the agent writes."""
    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="fake_claude:say `Hello!`",
    )
    page = sculptor_instance_.page

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # File browser should show the tree (workspace always has repo files)
    file_browser = get_file_browser_panel(page)
    expect(file_browser).to_be_visible()

    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()


@user_story("to see the file browser populated after creating a workspace without a prompt")
def test_file_browser_populates_after_workspace_created_without_prompt(sculptor_instance_: SculptorInstance) -> None:
    """File browser shows the file tree after creating a workspace without a prompt.

    When a workspace is created without a prompt, the agent enters a waiting state.
    The environment (clone) is still created asynchronously, and the file browser
    should populate with the cloned repo's files without needing to send a prompt first.
    """
    start_task_and_wait_for_ready(
        sculptor_instance_.page,
        workspace_name="No-Prompt Workspace",
    )
    page = sculptor_instance_.page

    # File browser panel should be visible
    file_browser = get_file_browser_panel(page)
    expect(file_browser).to_be_visible()

    # The file tree should populate with the cloned repo's files.
    # With the bug, this times out because the file list is never fetched
    # after the environment is created.
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Verify tree rows are present (the test project's repo has files)
    tree_rows = file_tree.get_tree_rows()
    expect(tree_rows.first).to_be_visible()


@user_story("to customize file browser behavior")
def test_settings_file_browser_section_visible(sculptor_instance_: SculptorInstance) -> None:
    """File Browser section is visible in the Settings page sidebar."""
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)

    # Find and click the "File browser" section in the sidebar
    file_browser_nav = settings_page.get_by_test_id(ElementIDs.SETTINGS_NAV_FILE_BROWSER)
    expect(file_browser_nav).to_be_visible()
    file_browser_nav.click()

    # Verify settings are visible
    settings_content = settings_page.get_by_test_id(ElementIDs.SETTINGS_CONTENT)
    expect(settings_content).to_contain_text("Default split ratio")
    expect(settings_content).to_contain_text("Tab close behavior")
    expect(settings_content).to_contain_text("Line wrapping")
    expect(settings_content).to_contain_text("Default diff view")


@user_story("to collapse all folders at once")
def test_collapse_all_folders_button(sculptor_instance_: SculptorInstance) -> None:
    """Collapse all folders button collapses expanded folders in the tree."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    expect(file_browser).to_be_visible()

    # Expand src/ folder (may already be expanded from auto-expand)
    _ensure_folder_expanded(page, "src")

    # App.tsx should now be visible inside src/
    app_row = file_browser.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row).to_be_visible()

    # Click collapse all button
    collapse_btn = file_browser.get_collapse_button()
    collapse_btn.click()

    # App.tsx should no longer be visible (folder collapsed)
    expect(app_row).not_to_be_visible()


@user_story("to collapse all change folders at once via the collapse button on the Changes tab")
def test_collapse_all_changes_folders_button(sculptor_instance_: SculptorInstance) -> None:
    """Collapse button on the Changes tab collapses expanded change folders."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)

    # Switch to the Changes tab
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # The changes tree auto-expands folders, so App.tsx should be visible inside src/
    app_row = changes_tree.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row).to_be_visible()

    # Click collapse all — should collapse change folders (not Browse folders)
    collapse_btn = file_browser.get_collapse_button()
    collapse_btn.click()

    # App.tsx should no longer be visible (folder collapsed)
    expect(app_row).not_to_be_visible()


_COMMIT_WITH_FILES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-collapse"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "feature.py",
        "content": "print('hello')\\n"
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


@user_story("to collapse all expanded commits via the collapse button on the Commits tab")
def test_collapse_all_commits_button(sculptor_instance_: SculptorInstance) -> None:
    """Collapse button on the Commits tab collapses expanded commit entries."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMIT_WITH_FILES_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Switch to the History tab
    file_browser = get_file_browser_panel(page)
    history_tab = file_browser.get_tab_history()
    expect(history_tab).to_be_visible()
    history_tab.click()

    history_panel = page.get_by_test_id(ElementIDs.HISTORY_PANEL)
    expect(history_panel).to_be_visible()

    # Click the commit to expand it and reveal its file list
    commit_entry = history_panel.get_by_test_id(ElementIDs.HISTORY_COMMIT_ENTRY).filter(has_text="Add feature.py")
    expect(commit_entry).to_be_visible()
    commit_entry.get_by_test_id(ElementIDs.HISTORY_COMMIT_MESSAGE).click()

    # The commit's file row should now be visible
    file_row = history_panel.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW).filter(has_text="feature.py")
    expect(file_row).to_be_visible()

    # Click collapse all — should collapse the expanded commit
    collapse_btn = file_browser.get_collapse_button()
    collapse_btn.click()

    # The file row should no longer be visible (commit collapsed)
    expect(file_row).not_to_be_visible()


# ---------------------------------------------------------------------------
# Diff Panel: Review All (Combined Diff View)
# ---------------------------------------------------------------------------


@user_story("to review all changed files at once")
def test_review_all_button_opens_combined_diff(sculptor_instance_: SculptorInstance) -> None:
    """Clicking 'Review all' opens the combined diff view tab showing all changed files."""
    _enable_review_all_via_settings(sculptor_instance_.page)
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Switch to Changes tab where Review All lives
    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    # Review All button should be visible after files are created
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()
    review_all_btn.click()

    # Diff panel should open
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # A "Review All" tab should appear in the tab bar
    diff_tabs = diff_panel.get_tabs()
    review_tab = diff_tabs.filter(has_text="Review All")
    expect(review_tab).to_be_visible()

    # The combined view should show multiple files' diffs
    # File section headers use data-filepath attribute
    expect(diff_panel).to_contain_text("README")
    expect(diff_panel).to_contain_text("App.tsx")


# Prompt that writes two files, commits them, then writes one more uncommitted file.
# After this runs the workspace has 2 committed files + 1 uncommitted file.
_COMMITTED_AND_UNCOMMITTED_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "committed_a.py",
        "content": "a = 1\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "committed_b.py",
        "content": "b = 2\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add committed files'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "uncommitted_c.py",
        "content": "c = 3\\n"
      }
    }
  ]
}`"""


@user_story("to review all branch files when clicking Review All")
def test_review_all_shows_all_branch_files(sculptor_instance_: SculptorInstance) -> None:
    """Review All defaults to All scope, showing both committed and uncommitted files.

    When a workspace has both committed changes (relative to the base branch)
    and uncommitted changes, clicking 'Review All' should show all of them
    since it defaults to the All scope.
    """
    page = sculptor_instance_.page
    _enable_review_all_via_settings(page)

    task_page = start_task_and_wait_for_ready(page, prompt=_COMMITTED_AND_UNCOMMITTED_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # The Changes tab (Uncommitted scope) should show only 1 uncommitted file
    task_page.activate_changes_panel(scope="uncommitted")

    file_browser = get_file_browser_panel(page)
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    # Only the uncommitted file should appear in the Uncommitted changes tree
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("uncommitted_c.py")

    # Click Review All — defaults to All scope, showing all branch changes
    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()
    review_all_btn.click()

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # The combined diff view should contain all files (committed + uncommitted)
    expect(diff_panel).to_contain_text("uncommitted_c.py")
    expect(diff_panel).to_contain_text("committed_a.py")
    expect(diff_panel).to_contain_text("committed_b.py")


@user_story("to switch between individual file and review-all tabs")
def test_switch_between_file_tab_and_review_all(sculptor_instance_: SculptorInstance) -> None:
    """Switching between a single-file tab and Review All shows the correct view."""
    _enable_review_all_via_settings(sculptor_instance_.page)
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open a single file first
    _open_file_in_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    diff_file_header = diff_panel.get_file_header()
    expect(diff_file_header).to_be_visible()
    expect(diff_file_header).to_contain_text("README")

    # Switch to Changes tab and click Review All
    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    review_all_btn = file_browser.get_review_all_button()
    review_all_btn.click()

    # Should now have 2 tabs (README + Review All)
    diff_tabs = diff_panel.get_tabs()
    expect(diff_tabs).to_have_count(2)

    # The single-file header should NOT be visible (combined view is active)
    expect(diff_file_header).not_to_be_visible()

    # Switch back to the README tab
    readme_tab = diff_tabs.filter(has_text="README")
    readme_tab.click()

    # File header should reappear for single-file view
    expect(diff_file_header).to_be_visible()
    expect(diff_file_header).to_contain_text("README")


# ---------------------------------------------------------------------------
# Diff Panel: "All" scope (vs-target-branch) diff rendering
# ---------------------------------------------------------------------------

# Prompt that shortens src/helpers.py (75 lines on main) down to 25 lines by
# removing the first six functions and the last four functions, then commits.
#
# This produces a two-hunk diff:
#   Hunk 1  @@ -1,32 +1,6 @@   — removes the add/subtract/.../cube group
#   Hunk 2  @@ -49,27 +23,3 @@  — removes the unique/chunk/format_name/truncate group
#
# There is a 16-line gap (main lines 33–48) between the two hunks.  Pierre's
# context-expansion loop accesses oldLines[32]…oldLines[47] to fill that gap.
# When oldLines is incorrectly fetched from HEAD (25 lines) rather than from
# the target branch (75 lines), those accesses all return undefined, causing
# Pierre to produce a zero-length AST and crash with:
#   renderHunks: oldLine and newLine are null, something is wrong
_SHORTEN_HELPERS_FILE_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "src/helpers.py",
        "content": "# Helper utilities for the project.\\n\\n\\ndef is_even(n):\\n    return n % 2 == 0\\n\\n\\ndef is_odd(n):\\n    return n % 2 != 0\\n\\n\\ndef clamp(value, min_val, max_val):\\n    return max(min_val, min(max_val, value))\\n\\n\\ndef reverse_string(s):\\n    return s[::-1]\\n\\n\\ndef count_vowels(s):\\n    return sum(1 for c in s.lower() if c in 'aeiou')\\n\\n\\ndef flatten(nested):\\n    return [item for sublist in nested for item in sublist]\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Remove first and last function groups from helpers'"
      }
    }
  ]
}`"""


@user_story("to view committed changes to an existing file in the All scope diff")
def test_all_scope_diff_renders_without_error_for_committed_file(sculptor_instance_: SculptorInstance) -> None:
    """Opening a committed file in the "All" scope should render without a Pierre crash.

    When the workspace branch has committed changes to a file that also exists
    in the target branch (main), opening that file in the "All changes" view
    (scope="vs-target-branch") used to crash Pierre with:

        renderHunks: oldLine and newLine are null, something is wrong

    The crash requires a two-hunk diff where there is a context-expansion gap
    between the hunks AND HEAD has fewer lines than the merge-base-aligned
    indices the gap loop tries to access.  src/helpers.py is 75 lines on main;
    after HEAD removes both the first and last function groups it shrinks to 25
    lines.  The 16-line gap between hunk 1 and hunk 2 causes Pierre to access
    oldLines[32]…oldLines[47].  With the bug, oldLines came from HEAD (only 25
    entries), so those accesses returned undefined and Pierre crashed.
    """
    page = sculptor_instance_.page

    # Capture uncaught JS exceptions AND console errors — Pierre's renderHunks
    # crash shows up as a console error (Pierre catches it internally).
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(err.message))
    page.on(
        "console",
        lambda msg: js_errors.append(msg.text) if msg.type == "error" else None,
    )

    task_page = start_task_and_wait_for_ready(page, prompt=_SHORTEN_HELPERS_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open Changes tab in "All" scope (vs-target-branch — the default scope).
    task_page.activate_changes_panel()

    file_browser = get_file_browser_panel(page)
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # helpers.py now has 25 lines on HEAD but 75 lines on main.  Clicking it
    # triggers the two-hunk render path that crashed Pierre.
    row = changes_tree.get_tree_rows().filter(has_text="helpers.py")
    expect(row.first).to_be_visible()
    row.first.click()

    # Diff panel should open and render successfully.
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel.get_unified_diff_views()).to_be_visible()

    # Wait for Pierre to render diff content (file-line fetch + Shiki tokenization).
    expect(diff_panel).to_contain_text("Helper utilities")

    # Pierre must not have crashed with a renderHunks error.
    render_hunks_errors = [e for e in js_errors if "renderHunks" in e]
    assert not render_hunks_errors, f"Pierre renderHunks crash: {render_hunks_errors[0]}"


# ---------------------------------------------------------------------------
# Diff Panel: Split / Unified View Toggle
# ---------------------------------------------------------------------------


@user_story("to compare files side-by-side")
def test_split_view_toggle(sculptor_instance_: SculptorInstance) -> None:
    """Split view toggle switches between unified and split diff views."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open from Changes tab so the file opens as a diff view (PierreDiffView)
    # rather than a read-only preview (ReadOnlyPreview from the Browse tab).
    _open_file_in_changes_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Unified view should be the default
    unified_view = diff_panel.get_unified_diff_views()
    expect(unified_view).to_be_visible()

    # Click split view toggle
    split_toggle = diff_panel.get_split_view_toggle()
    split_toggle.click()

    # Split view should now be visible
    split_view = diff_panel.get_split_view()
    expect(split_view).to_be_visible()

    # Toggle back to unified
    split_toggle.click()
    expect(unified_view).to_be_visible()


@user_story("to toggle between unified and split view when reviewing all changes")
def test_split_view_toggle_works_for_combined_diff(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the split/unified toggle should change the view mode in the combined diff."""
    _enable_review_all_via_settings(sculptor_instance_.page)
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Ensure the File Browser panel is visible before switching tabs
    file_browser = get_file_browser_panel(page)
    if not file_browser.is_visible():
        page.get_by_test_id(ElementIDs.PANEL_ICON_FILES).click()

    # Open the combined "Review All" diff via the Changes tab
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()
    review_all_btn.click()

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Verify the diff starts in unified mode
    expect(diff_panel.get_unified_diff_views().first).to_be_visible()
    expect(diff_panel.get_split_view()).to_have_count(0)

    # Click the split view toggle
    split_toggle = diff_panel.get_split_view_toggle()
    expect(split_toggle).to_be_visible()
    split_toggle.click()

    # Verify the diff switched to split mode for modified files.
    # Newly added files (App.tsx, Header.tsx) remain in unified mode since
    # there is no "before" side to split, so we only check that at least one
    # split view appeared (README.md is a modified file).
    expect(diff_panel.get_split_view().first).to_be_visible()


@user_story("to have my split view preference persist when closing and reopening the diff panel")
def test_split_view_toggle_persists_across_panel_reopen(sculptor_instance_: SculptorInstance) -> None:
    """Toggling the view type should persist when the diff panel is closed and reopened."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open from Changes tab so the file opens as a diff view (PierreDiffView)
    # rather than a read-only preview (ReadOnlyPreview from the Browse tab).
    _open_file_in_changes_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Ensure we start in unified mode by toggling until unified is active.
    # The view type is a global user preference that may have been changed by
    # a previous test in the shared instance.
    split_toggle = diff_panel.get_split_view_toggle()
    expect(split_toggle).to_be_visible()
    if split_toggle.get_attribute("data-state") == "split":
        split_toggle.click()
    expect(split_toggle).to_have_attribute("data-state", "unified")

    # Toggle to split view
    split_toggle.click()
    expect(diff_panel.get_split_view().first).to_be_visible()

    # Close the diff panel via the dedicated close-panel button.  (Closing the
    # last tab now leaves the panel open with a placeholder, so it would not
    # exercise the "reopen" code path.)
    diff_panel.get_close_panel_button().click()
    expect(diff_panel).not_to_be_visible()

    # Reopen the file from the Changes tab
    _open_file_in_changes_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Verify split mode persisted across close/reopen
    expect(diff_panel.get_split_view().first).to_be_visible()
    expect(diff_panel.get_unified_diff_views()).to_have_count(0)


# ---------------------------------------------------------------------------
# Diff Panel: Line Wrap Toggle
# ---------------------------------------------------------------------------


@user_story("to toggle line wrapping on and off in the diff view")
def test_line_wrap_toggle(sculptor_instance_: SculptorInstance) -> None:
    """Line wrap toggle switches between wrap and scroll overflow modes."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    _open_file_in_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    wrap_toggle = diff_panel.get_line_wrap_toggle()
    expect(wrap_toggle).to_be_visible()

    # Click the toggle twice to cycle through both states and verify it
    # remains visible and clickable each time.
    wrap_toggle.click()
    expect(wrap_toggle).to_be_visible()

    wrap_toggle.click()
    expect(wrap_toggle).to_be_visible()


@user_story("to have my line wrap preference persist when closing and reopening the diff panel")
def test_line_wrap_toggle_persists_across_panel_reopen(sculptor_instance_: SculptorInstance) -> None:
    """Toggling the line wrap mode should persist when the diff panel is closed and reopened."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    _open_file_in_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    wrap_toggle = diff_panel.get_line_wrap_toggle()
    expect(wrap_toggle).to_be_visible()

    # Ensure we start in "wrap" mode (the default). The wrap toggle has an
    # active highlight class when wrapping is enabled.
    if "activeControl" not in (wrap_toggle.get_attribute("class") or ""):
        wrap_toggle.click()
    expect(wrap_toggle).to_have_class(re.compile(r"activeControl"))

    # Toggle to scroll mode — the active highlight should disappear.
    wrap_toggle.click()
    expect(wrap_toggle).not_to_have_class(re.compile(r"activeControl"))

    # Close the diff panel via the dedicated close-panel button.  (Closing the
    # last tab now leaves the panel open with a placeholder.)
    diff_panel.get_close_panel_button().click()
    expect(diff_panel).not_to_be_visible()

    # Reopen the file in the diff panel
    _open_file_in_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Verify scroll mode persisted across close/reopen
    wrap_toggle = diff_panel.get_line_wrap_toggle()
    expect(wrap_toggle).to_be_visible()
    expect(wrap_toggle).not_to_have_class(re.compile(r"activeControl"))


# ---------------------------------------------------------------------------
# Diff Panel: File Header with Line Statistics
# ---------------------------------------------------------------------------


@user_story("to see how many lines were added or removed in a file")
def test_diff_file_header_shows_line_stats(sculptor_instance_: SculptorInstance) -> None:
    """Diff file header shows added/removed line counts."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open the file from the Changes tab so it renders as a diff with line stats.
    # The Browse tab opens a read-only preview with no line stats.
    _open_file_in_changes_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_be_visible()

    # The header should show + and - line stats for a newly created file
    expect(diff_header).to_contain_text("+")


# ---------------------------------------------------------------------------
# Diff Panel: Tab Switching Shows Correct File
# ---------------------------------------------------------------------------


@user_story("to switch between open files using tabs")
def test_clicking_tab_switches_displayed_file(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a different tab in the diff panel switches the displayed file."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open README.md first
    _open_file_in_diff(page, "README")
    diff_panel = get_diff_panel_from_page(page)
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("README")

    # Expand src/ folder (may already be expanded from auto-expand) and open App.tsx
    _ensure_folder_expanded(page, "src")
    file_browser = get_file_browser_panel(page)
    app_row = file_browser.get_tree_rows().filter(has_text="App.tsx")
    app_row.first.click()

    # Header should now show App.tsx
    expect(diff_header).to_contain_text("App.tsx")

    # Click back to README tab
    readme_tab = diff_panel.get_tab_by_name("README")
    readme_tab.click()

    # Header should switch back to README
    expect(diff_header).to_contain_text("README")


# Build a 200-line Python file for FakeClaude's write_file command.
# JSON newlines are represented as \\n in the prompt string.
_LONG_FILE_CONTENT = "\\n".join(f"x{i} = {i}" for i in range(200))

# Strategy: first write-and-commit a 200-line src/main.py, then edit three
# lines at widely-spaced positions.  This produces a multi-hunk diff where
# Pierre must use oldLines/newLines to reconstruct unchanged regions between
# hunks for syntax highlighting.  When the stale oldLines/newLines from the
# short README (~3 lines) are used for a 200-line file, Shiki throws
# "Invalid decoration position" because decoration positions reference lines
# beyond the code length.
_MODIFY_EXISTING_FILES_PROMPT = f"""\
fake_claude:multi_step `{{
  "steps": [
    {{
      "command": "write_file",
      "args": {{
        "file_path": "src/main.py",
        "content": "{_LONG_FILE_CONTENT}\\n"
      }}
    }},
    {{
      "command": "bash",
      "args": {{
        "command": "git add src/main.py && git commit -m 'long file'"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "src/main.py",
        "old_string": "x5 = 5",
        "new_string": "x5 = 999"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "src/main.py",
        "old_string": "x100 = 100",
        "new_string": "x100 = 999"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "src/main.py",
        "old_string": "x195 = 195",
        "new_string": "x195 = 999"
      }}
    }},
    {{
      "command": "write_file",
      "args": {{
        "file_path": "README.md",
        "content": "# Updated Project\\nBrief description.\\n"
      }}
    }}
  ]
}}`"""


@user_story("to switch between diff tabs without seeing Shiki decoration errors")
def test_tab_switch_no_shiki_decoration_error(sculptor_instance_: SculptorInstance) -> None:
    """Switching between modified-file tabs must not flash Shiki decoration errors.

    The bug only triggers for modified files (status "M") with multi-hunk diffs,
    where Pierre needs oldLines/newLines to reconstruct unchanged regions for
    syntax highlighting.
    """
    page = sculptor_instance_.page

    console_errors: list[str] = []

    def _on_console(msg: ConsoleMessage) -> None:
        if msg.type == "error":
            console_errors.append(msg.text)

    page.on("console", _on_console)

    task_page = start_task_and_wait_for_ready(page, prompt=_MODIFY_EXISTING_FILES_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the short file first — loads its oldLines/newLines (~2-3 lines).
    _open_file_in_diff(page, "README")
    diff_panel = get_diff_panel_from_page(page)
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("README")

    # Wait for useFileLines to complete its async fetch so that both oldLines
    # and newLines are populated and FileDiff (with Shiki decorations) is used.
    # ReadOnlyPreview renders file content via Pierre's shadow DOM, so
    # expect().to_contain_text() cannot observe it — a fixed delay is the
    # only viable approach here.
    page.wait_for_timeout(2000)

    # Switch to the long file — this is the tab switch that triggers the bug.
    _ensure_folder_expanded(page, "src")
    _open_file_in_diff(page, "main.py")
    expect(diff_header).to_contain_text("main.py")

    # Allow any async error to surface.  Same limitation: Pierre's shadow DOM
    # content is not observable by Playwright's text matchers.
    page.wait_for_timeout(1000)

    # The bug: stale README lines (~3 lines) + main.py diff (200 lines) →
    # ShikiError: Invalid decoration position.
    shiki_errors = [e for e in console_errors if "ShikiError" in e or "Invalid decoration" in e]
    assert shiki_errors == [], f"Shiki decoration errors during tab switch: {shiki_errors}"


# ---------------------------------------------------------------------------
# File Browser: Search Result Filtering
# ---------------------------------------------------------------------------


@user_story("to narrow down the file tree using search")
def test_file_search_filters_visible_rows(sculptor_instance_: SculptorInstance) -> None:
    """Typing in the file search filters the tree to show only matching files."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Open search
    search_btn = file_browser.get_search_button()
    search_btn.click()
    search_input = file_browser.get_search_input()
    expect(search_input).to_be_visible()

    # Search for "Header" — only Header.tsx and its parent folders should show
    search_input.fill("Header")

    # Header should remain visible in the filtered tree
    header_row = file_tree.get_tree_rows().filter(has_text="Header")
    expect(header_row.first).to_be_visible()

    # README should NOT be visible in the filtered results
    readme_row = file_tree.get_tree_rows().filter(has_text="README")
    expect(readme_row).to_have_count(0)


@user_story("to dismiss search with the escape key")
def test_file_search_escape_closes(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Escape in the search input closes the search bar."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    search_btn = file_browser.get_search_button()
    search_btn.click()

    search_input = file_browser.get_search_input()
    expect(search_input).to_be_visible()

    # Press Escape to close search
    search_input.press("Escape")
    expect(search_input).not_to_be_visible()


@user_story("to see a clear empty state when no files match my search")
def test_file_search_no_matches_shows_empty_state(sculptor_instance_: SculptorInstance) -> None:
    """Searching for a string that matches no files shows 'No matches' instead of the full tree."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Open search and type a query that won't match any file
    search_btn = file_browser.get_search_button()
    search_btn.click()
    search_input = file_browser.get_search_input()
    search_input.fill("zzz_definitely_no_match")

    # The search bar should show "0 found"
    expect(file_browser).to_contain_text("0 found")

    # The file tree should NOT be visible (replaced by "No matches")
    expect(file_tree).not_to_be_visible()

    # "No matches" message should appear
    expect(file_browser).to_contain_text("No matches")

    # README should not be visible — the tree must not fall back to showing all files
    readme_row = file_browser.get_tree_rows().filter(has_text="README")
    expect(readme_row).to_have_count(0)


@user_story("to search files by exact substring, not fuzzy match")
def test_file_search_uses_exact_substring_matching(sculptor_instance_: SculptorInstance) -> None:
    """A near-miss typo should not match files — only exact substrings of the path."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Open search
    search_btn = file_browser.get_search_button()
    search_btn.click()
    search_input = file_browser.get_search_input()

    # "Headr" is close to "Header" but should NOT fuzzy-match
    search_input.fill("Headr")

    expect(file_browser).to_contain_text("0 found")

    # Header.tsx should not appear
    header_row = file_browser.get_tree_rows().filter(has_text="Header")
    expect(header_row).to_have_count(0)


@user_story("to collapse folders while searching to focus on specific results")
def test_file_search_folders_are_collapsible(sculptor_instance_: SculptorInstance) -> None:
    """Folder nodes remain collapsible/expandable during an active search."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Open search and search for ".tsx" to match both App.tsx and Header.tsx
    search_btn = file_browser.get_search_button()
    search_btn.click()
    search_input = file_browser.get_search_input()
    search_input.fill(".tsx")

    # Both files should be visible (folders auto-expanded on search activation)
    app_row = file_tree.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row.first).to_be_visible()
    header_row = file_tree.get_tree_rows().filter(has_text="Header")
    expect(header_row.first).to_be_visible()

    # Find the "src" folder row — it should be expanded
    # Note: with compaction, the folder may show as "src/components" but "src" should exist
    src_row = file_tree.get_tree_rows().filter(has_text="src").first
    expect(src_row).to_have_attribute("aria-expanded", "true")

    # Click the src folder to collapse it
    src_row.click()
    expect(src_row).to_have_attribute("aria-expanded", "false")

    # App.tsx should no longer be visible (it's inside the collapsed src folder)
    expect(app_row).not_to_be_visible()

    # Click again to re-expand
    src_row.click()
    expect(src_row).to_have_attribute("aria-expanded", "true")

    # App.tsx should be visible again
    expect(app_row.first).to_be_visible()


# ---------------------------------------------------------------------------
# File Browser: Changes Tab (Flat List View)
# ---------------------------------------------------------------------------


@user_story("to see all changed files in a flat list")
def test_changes_tab_shows_changed_files(sculptor_instance_: SculptorInstance) -> None:
    """The Changes tab shows a flat list of all changed files with status indicators."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Switch to Changes tab
    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    changes_tab.click()

    # Changes tree should appear
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # All three created files should be visible
    expect(changes_tree).to_contain_text("README")
    expect(changes_tree).to_contain_text("App.tsx")
    expect(changes_tree).to_contain_text("Header")


@user_story("to open a diff from the changes list")
def test_changes_tab_click_opens_diff(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Changes tab opens its diff panel."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Switch to Changes tab
    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    changes_tab.click()

    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # Click on a file in the changes list
    readme_row = changes_tree.get_tree_rows().filter(has_text="README")
    readme_row.first.click()

    # Diff panel should open
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_contain_text("README")


# ---------------------------------------------------------------------------
# Diff Panel: In-File Search
# ---------------------------------------------------------------------------


@user_story("to find text within a diff")
def test_in_file_search_bar(sculptor_instance_: SculptorInstance) -> None:
    """The in-file search bar opens and shows match count for queries."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    _open_file_in_diff(page, "README")

    # README.md may render as markdown by default; in rendered mode the
    # find-in-file button is hidden. Force the source view.
    _ensure_render_mode(page, "source")

    # The in-file search bar should not be visible by default
    diff_panel = get_diff_panel_from_page(page)
    search_bar = diff_panel.get_search_bar()
    expect(search_bar).not_to_be_visible()

    # Click the "Find in file" button in the diff tab bar
    find_button = diff_panel.get_find_in_file_button()
    find_button.click()

    # Search bar should appear
    expect(search_bar).to_be_visible()

    search_input = diff_panel.get_search_input()
    expect(search_input).to_be_visible()

    # Type a search query
    search_input.fill("Test Project")

    # Click the find button again to toggle search off
    find_button.click()
    expect(search_bar).not_to_be_visible()


@user_story("to find text within a file opened from the Browse tab")
def test_in_file_search_works_in_file_view(sculptor_instance_: SculptorInstance) -> None:
    """Find-in-file search finds matches in a read-only file view (Browse tab)."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Opening from the file tree (Browse tab) renders a ReadOnlyPreview,
    # not a diff. The search must still find matches inside the file content.
    _open_file_in_diff(page, "README")

    # README.md may render as markdown by default; the search hook walks
    # Pierre's DOM, so force the source view.
    _ensure_render_mode(page, "source")

    diff_panel = get_diff_panel_from_page(page)
    find_button = diff_panel.get_find_in_file_button()
    find_button.click()

    search_bar = diff_panel.get_search_bar()
    expect(search_bar).to_be_visible()

    # README.md contains "Test Project" — the search should find it.
    search_input = diff_panel.get_search_input()
    search_input.fill("Test Project")

    # The search should report "1 of N" — not "No results".
    expect(search_bar).to_contain_text("1 of")


@user_story("to find text within the combined diff view")
def test_in_file_search_works_in_review_all(sculptor_instance_: SculptorInstance) -> None:
    """Find-in-file search finds matches in the Review All combined diff view."""
    _enable_review_all_via_settings(sculptor_instance_.page)
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Switch to Changes tab and open the Review All combined diff
    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()
    changes_tab.click()

    review_all_btn = file_browser.get_review_all_button()
    expect(review_all_btn).to_be_visible()
    review_all_btn.click()

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Wait for the combined view to render file content
    expect(diff_panel).to_contain_text("README")
    expect(diff_panel).to_contain_text("App.tsx")

    # Open find-in-file search bar
    find_button = diff_panel.get_find_in_file_button()
    find_button.click()

    search_bar = diff_panel.get_search_bar()
    expect(search_bar).to_be_visible()

    # Search for text that exists in the README.md diff content
    search_input = diff_panel.get_search_input()
    search_input.fill("Test Project")

    # The search should find at least one match (shown as "1 of N")
    expect(search_bar).to_contain_text("1 of")


# ---------------------------------------------------------------------------
# Diff Panel: New Files from Follow-up Messages
# ---------------------------------------------------------------------------


@user_story("to see new files appear in the file tree during a conversation")
def test_new_files_appear_after_followup_message(sculptor_instance_: SculptorInstance) -> None:
    """Files created in a follow-up message appear in the file browser."""
    task_page = _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Verify initial files are present
    expect(file_tree).to_contain_text("README")

    # Send a follow-up message to create another file
    chat_panel = task_page.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:write_file `{
  "file_path": "CHANGELOG.md",
  "content": "# Changelog\\n\\n## v1.0.0\\n- Initial release\\n"
}`""",
    )

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The new file should appear in the tree
    expect(file_tree).to_contain_text("CHANGELOG")


# ---------------------------------------------------------------------------
# File Browser: Folder Expand / Collapse
# ---------------------------------------------------------------------------


@user_story("to navigate into nested folders")
def test_folder_expand_and_collapse(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a folder row toggles its expansion, showing or hiding children."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # src/ folder should be visible
    src_row = file_browser.get_tree_rows().filter(has_text="src")
    expect(src_row.first).to_be_visible()

    # App.tsx should not be visible initially (folder collapsed)
    app_row = file_browser.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row).not_to_be_visible()

    # Expand src/
    src_row.first.click()
    expect(app_row.first).to_be_visible()

    # Collapse src/ by clicking again
    src_row.first.click()
    expect(app_row).not_to_be_visible()


# ---------------------------------------------------------------------------
# Diff Panel: Closing Panel via Close Button
# ---------------------------------------------------------------------------


@user_story("to close the diff panel entirely")
def test_close_diff_panel_button(sculptor_instance_: SculptorInstance) -> None:
    """The close-panel button on the diff tab bar hides the entire diff panel."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    _open_file_in_diff(page, "README")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Click the dedicated close-panel button (distinct from the per-tab close)
    diff_panel.get_close_panel_button().click()

    expect(diff_panel).not_to_be_visible()


# ---------------------------------------------------------------------------
# File Browser: Refresh Button
# ---------------------------------------------------------------------------


@user_story("to refresh the file listing after direct repo changes")
def test_refresh_button_reflects_file_operations(sculptor_instance_: SculptorInstance) -> None:
    """Refresh button picks up added, deleted, edited, and renamed files."""
    task_page = _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Verify initial state: README.md, src/App.tsx, src/components/Header.tsx
    expect(file_tree).to_contain_text("README")

    # Perform file operations via the agent: add, delete, edit, rename
    chat_panel = task_page.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "CHANGELOG.md",
        "content": "# Changelog\\n\\n## v1.0.0\\n- Initial release\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "rm src/components/Header.tsx"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "README.md",
        "old_string": "# Test Project",
        "new_string": "# Updated Project"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "mv src/App.tsx src/Main.tsx"
      }
    }
  ]
}`""",
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Click refresh to re-fetch the file listing
    refresh_btn = file_browser.get_refresh_button()
    refresh_btn.click()

    # Verify added file appears in file tree
    expect(file_tree).to_contain_text("CHANGELOG")

    # Verify deleted file is gone from file tree
    header_row = file_tree.get_tree_rows().filter(has_text="Header")
    expect(header_row).to_have_count(0)

    # Verify renamed file: App.tsx gone, Main.tsx present
    app_row = file_tree.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row).to_have_count(0)
    _ensure_folder_expanded(page, "src")
    expect(file_tree).to_contain_text("Main.tsx")

    # Verify the changes tab also reflects the operations
    changes_tab = file_browser.get_tab_changes()
    changes_tab.click()

    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # Added file should be listed
    expect(changes_tree).to_contain_text("CHANGELOG")
    # Edited file should be listed
    expect(changes_tree).to_contain_text("README")


def _get_workspace_working_dir(sculptor_instance: SculptorInstance) -> Path:
    """Find the clone workspace's working directory (sculptor_folder/workspaces/*/code/).

    After a workspace is created via the UI (clone mode), the clone lives at
    ``sculptor_folder / "workspaces" / env_id / "code"``.  This helper
    locates it by scanning the workspaces directory.
    """
    workspaces_dir = sculptor_instance.sculptor_folder / "workspaces"
    code_dirs = sorted(workspaces_dir.glob("*/code"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert code_dirs, f"No workspace clone found under {workspaces_dir}"
    return code_dirs[0]


@user_story("to see files created outside the agent in the uncommitted tab after refresh")
def test_refresh_button_updates_uncommitted_tab_for_external_changes(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Refresh button updates the Uncommitted tab for files created outside the agent.

    When a user creates a file via the terminal (not through the agent), clicking
    the refresh button should update both the file tree AND the Uncommitted tab.
    """
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    file_tree = file_browser.get_file_tree()
    expect(file_tree).to_be_visible()

    # Create a new file directly in the workspace's clone directory, bypassing
    # the agent.  This simulates a user creating a file in the terminal.
    workspace_dir = _get_workspace_working_dir(sculptor_instance_)
    new_file_path = workspace_dir / "EXTERNAL_FILE.txt"
    new_file_path.write_text("Created outside the agent.\n")

    # Click refresh
    refresh_btn = file_browser.get_refresh_button()
    refresh_btn.click()

    # The file tree (All tab) should now show the new file
    expect(file_tree).to_contain_text("EXTERNAL_FILE")

    # Switch to the Uncommitted tab — the new file should appear there too
    changes_tab = file_browser.get_tab_changes()
    changes_tab.click()

    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # The externally created file should be listed as uncommitted
    expect(changes_tree).to_contain_text("EXTERNAL_FILE")


# ---------------------------------------------------------------------------
# Changes Tab: Count Badge
# ---------------------------------------------------------------------------


@user_story("to see how many files have changed at a glance")
def test_changes_tab_shows_count(sculptor_instance_: SculptorInstance) -> None:
    """The Changes filter tab shows a count of changed files."""
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    file_browser = get_file_browser_panel(page)
    changes_tab = file_browser.get_tab_changes()
    expect(changes_tab).to_be_visible()

    # The changes tab shows the count of all changed files vs the target branch.
    # The mock repo has 2 committed files on the testing branch (src/app.py,
    # stuff.txt) plus 3 uncommitted files from the agent prompt = 5 total.
    expect(changes_tab).to_contain_text("5")


@user_story("to see changes cleared after committing files")
def test_changes_tab_clears_after_commit(sculptor_instance_: SculptorInstance) -> None:
    """The Changes tab should be empty after all modified files are committed."""
    task_page = _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Switch to Changes tab (Uncommitted scope) and verify files are listed
    task_page.activate_changes_panel(scope="uncommitted")

    file_browser = get_file_browser_panel(page)
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # All 3 changed files (plus ancestor directories) should be present
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.first).to_be_visible()

    # Commit all changes via the agent
    chat_panel = task_page.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:bash `{"command": "git add -A && git commit -m \'Add files\'"}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # After commit, the Changes tab should show no changed files.
    # The chain — bash subprocess → backend git polling → WebSocket push →
    # frontend store update → React rerender — needs more headroom under
    # high-parallelism CI than the original 10s budget allowed.
    expect(tree_rows).to_have_count(0)


# ---------------------------------------------------------------------------
# Diff Panel: Cmd+W Closes Active Diff Tab
# ---------------------------------------------------------------------------


@user_story("to close the active diff tab via keyboard")
def test_cmd_w_closes_active_diff_tab(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Cmd+W with the diff panel open closes the active diff tab.

    When multiple diff tabs are open, Cmd+W should close only the active tab
    and keep the panel open with the remaining tabs.  Closing the last tab
    via Cmd+W leaves the panel open showing the empty-state placeholder, and
    the workspace tab is not affected.
    """
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open two files in the diff panel
    _open_file_in_diff(page, "README")
    diff_panel = get_diff_panel_from_page(page)
    diff_tabs = diff_panel.get_tabs()
    expect(diff_tabs).to_have_count(1)

    _ensure_folder_expanded(page, "src")
    _open_file_in_diff(page, "App.tsx")
    expect(diff_tabs).to_have_count(2)
    expect(diff_panel).to_be_visible()

    # Blur the active element so the keypress reaches the app-level handler
    blur_active_element(page)

    # Press Cmd+W — should close the active diff tab, not the workspace
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")

    # One tab should remain, panel still visible
    expect(diff_tabs).to_have_count(1)
    expect(diff_panel).to_be_visible()

    # Workspace tab should still be present (not closed)
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(1)

    # Press Cmd+W again — closes the last diff tab.  The panel stays open
    # (showing the placeholder) rather than collapsing.
    blur_active_element(page)
    page.keyboard.press(f"{mod_key}+w")

    expect(diff_tabs).to_have_count(0)
    expect(diff_panel).to_be_visible()
    expect(diff_panel).to_contain_text("Open a file to view it")

    # Workspace tab should still be present
    expect(workspace_tabs).to_have_count(1)


# ---------------------------------------------------------------------------
# Copy file path: absolute paths outside the repo
# ---------------------------------------------------------------------------

WRITE_ABSOLUTE_PATH_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "/tmp/sculptor-test-outside-repo.txt",
  "content": "This file lives outside the repo.\\n"
}`"""


@user_story("to copy the correct path for a file outside the repo")
def test_copy_file_path_for_absolute_path_file(sculptor_instance_: SculptorInstance) -> None:
    """Copy file path should return the correct absolute path for files outside the repo.

    When the agent writes a file with an absolute path (outside the repo),
    the diff panel's "Copy file path" should copy just the absolute path,
    not prepend the repo path to it.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=WRITE_ABSOLUTE_PATH_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the file's full diff via the alpha file chip popover.
    file_chip = page.get_by_test_id(ElementIDs.ALPHA_CHAT_FILE_CHIP).filter(has_text="sculptor-test-outside-repo.txt")
    expect(file_chip.first).to_be_visible()
    file_chip.first.click()

    popover = page.get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_POPOVER)
    expect(popover).to_be_visible()
    popover.get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN).click()

    # The diff panel should open with a file header showing the file path.
    diff_panel = get_diff_panel_from_page(page)
    diff_header = diff_panel.get_file_header()
    expect(diff_header).to_be_visible()

    # Install a clipboard interceptor so we can read what was written.
    install_clipboard_interceptor(page)

    # Click the "..." dropdown button in the diff header to open the file menu.
    menu_trigger = diff_panel.get_file_header_menu_trigger()
    menu_trigger.click()

    # Click "Copy file path" from the dropdown menu.
    copy_path_item = page.get_by_test_id("copy-path")
    expect(copy_path_item).to_be_visible()
    copy_path_item.click()

    # Verify the clipboard contains the correct absolute path, not repo_path + "/" + absolute_path.
    clipboard_value = read_intercepted_clipboard(page)
    assert clipboard_value is not None, "Clipboard should contain a value after clicking Copy file path"
    assert clipboard_value == "/tmp/sculptor-test-outside-repo.txt", (
        f"Expected clipboard to contain '/tmp/sculptor-test-outside-repo.txt', got '{clipboard_value}'"
    )


@user_story("to close the workspace tab via keyboard when no diff tabs are open")
def test_cmd_w_closes_workspace_when_diff_panel_closed(sculptor_instance_: SculptorInstance) -> None:
    """Pressing Cmd+W without an open diff panel closes the workspace tab.

    With the diff panel closed entirely, Cmd+W falls through to the default
    behavior of closing the workspace tab.
    """
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open a file in the diff panel, then close the panel itself (not just
    # the tab — closing the last tab now keeps the panel open).
    _open_file_in_diff(page, "README")
    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    diff_panel.get_close_panel_button().click()
    expect(diff_panel).not_to_be_visible()

    # Verify workspace tab exists
    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    expect(workspace_tabs).to_have_count(1)

    # Blur the active element and press Cmd+W — should close the workspace tab
    blur_active_element(page)
    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+w")

    # Workspace tab should be closed
    expect(workspace_tabs).to_have_count(0)


@user_story("to not see a useless splitter when viewing a newly added file")
def test_split_handle_hidden_for_new_file(sculptor_instance_: SculptorInstance) -> None:
    """Split column handle should not appear for newly added files.

    When a file has status "A" (added), there is no "before" content to compare
    against, so showing a side-by-side splitter handle is meaningless.
    """
    _start_task_with_files(sculptor_instance_)
    page = sculptor_instance_.page

    # Open a genuinely new file (App.tsx does not exist in the initial repo).
    _ensure_folder_expanded(page, "src")
    _open_file_in_diff(page, "App.tsx")

    diff_panel = get_diff_panel_from_page(page)
    expect(diff_panel).to_be_visible()

    # Switch to split mode.
    split_toggle = diff_panel.get_split_view_toggle()
    expect(split_toggle).to_be_visible()
    split_toggle.click()

    # Even in split mode, the handle must not appear for a new file.
    handle = diff_panel.get_split_column_handle()
    expect(handle).to_have_count(0)


# ---------------------------------------------------------------------------
# Changes Tab: Renamed/Moved Files
# ---------------------------------------------------------------------------

# Move a file that exists on main (the target branch) to a new directory.
# The vs-target-branch diff will detect this as a rename (status R).
_RENAME_FILE_PROMPT = """\
fake_claude:bash `{
  "command": "mkdir -p lib && git mv src/helpers.py lib/helpers.py && git add -A && git commit -m 'Move helpers to lib'"
}`"""


@user_story("to see moved files rendered cleanly with R status and no redundant rename label")
def test_moved_file_shows_r_status_without_rename_label(sculptor_instance_: SculptorInstance) -> None:
    """Moved files should show R status without a redundant old→new name label.

    When a file is moved to a new folder without changing its name, the
    Changes tab should show only the file in its new location with an R
    (renamed) status indicator — no "oldName →" label that duplicates the
    filename.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_RENAME_FILE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open Changes tab (default All scope = vs-target-branch)
    task_page.activate_changes_panel()

    file_browser = get_file_browser_panel(page)
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # The moved file should appear in the tree
    file_row = changes_tree.get_tree_rows().filter(has_text="helpers.py")
    expect(file_row).to_be_visible()

    # Status should be "R" (renamed)
    status = file_row.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW_STATUS)
    expect(status).to_have_text("R")

    # The row must NOT contain the "→" rename arrow — the old name label
    # should not be rendered since the filename itself didn't change.
    expect(file_row).not_to_contain_text("\u2192")
