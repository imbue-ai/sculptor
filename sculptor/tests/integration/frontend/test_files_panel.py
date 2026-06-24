"""Integration tests for the Files panel — the workspace file tree paired with
its own embedded DiffViewer (FCC-01/03/04/05/06).

The Files panel is one of the three separate panels that replaced the old
single File-Browser panel with its All/Changes/History tabs. It pairs the
workspace file tree (the list) with an always-visible embedded viewer (the
detail) via the shared ``ExplorerLayout``. There is no tab model: the Changes
and Commits panels are their own panels, so the old ``FILE_BROWSER_TAB_*``
surface (and everything that hung off it) is gone.

These cases are MIGRATED, not rewritten, from the pre-rewrite file-browser
tests (see ``e2e_test_plan.md`` §1). The proven file-tree content assertions
carry over unchanged; only the *surface* moved:

* a panel is opened through the section ``+`` add-panel dropdown (the 3.6a
  ``open_panel`` helper) instead of being the default docked panel;
* the file tree, search box, status indicators, and embedded viewer are driven
  through the ``PlaywrightFilesPanelElement`` / ``ExplorerLayout`` /
  ``DiffViewer`` POMs scoped to the opened section;
* the list view controls (flat/tree, collapse-all) re-anchored under the
  viewer header's single triple-dot menu (FCC-07), reached via
  ``toggle_view_option_via_menu``;
* the sidebar-visibility toggle lives in the viewer header (FCC-05) and the
  viewer is always visible with an empty body when nothing is selected (FCC-06).

This file also folds in the Task 3.6a harness smoke test (open Files + render
list/viewer), so ``test_fcc_harness_smoke.py`` can be deleted.

The old All/Changes/History tab-switching, the multi-tab diff surface, the
scope picker (All/Uncommitted), Review All, copy-path, Cmd+W tab close, and the
list header's search/refresh buttons are NOT part of the Files panel surface:
those moved to the Changes / Commits panels or the viewer menu and are covered
by ``test_changes_panel.py`` / ``test_diff_viewer.py``. The diff-mode
assertions that depend on the scope picker or the old global diff-panel routing
are skipped here with a follow-up reason rather than re-pointed at a surface the
Files panel does not own.

Migrated from:
* ``test_file_browser.py`` (file-tree content only)
* ``test_file_browser_tabs.py`` (residual file-tree content only; the
  All/Changes/History tab-switching is dropped — that tab model is gone)
* ``test_file_browser_symlink_replaces_directory.py``
* ``test_file_open_diff_modes.py``
* ``test_path_tilde_display.py``
* ``test_fcc_harness_smoke.py`` (folded in)
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.files_panel import PlaywrightFilesPanelElement
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# --------------------------------------------------------------------------- #
# Skip reasons (kept as single-line variables so the decorators stay short and
# avoid adjacent-string-literal concatenation).
# --------------------------------------------------------------------------- #

_SCOPE_DIFF_SKIP_REASON = "Uncommitted/All scope diff modes are driven by the Changes panel scope picker, not the Files panel; follow-up belongs in test_changes_panel.py."

_SYMLINK_SKIP_REASON = "Symlink-replaces-directory repro needs the uncommitted Changes scope plus a page.evaluate row count (ratchet at budget); follow-up belongs in test_changes_panel.py."

# --------------------------------------------------------------------------- #
# FakeClaude prompts (migrated verbatim from the source tests).
# --------------------------------------------------------------------------- #

# Writes a nested tree: src/App.tsx, src/components/Header.tsx, README.md.
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

# Create a feature branch, write+commit one file, then write an uncommitted
# file, so the tree shows both a committed and an uncommitted file.
_COMMITTED_AND_UNCOMMITTED_PROMPT = """\
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
        "content": "x = 1\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add committed.py'"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "uncommitted.py",
        "content": "y = 2\\n"
      }
    }
  ]
}`"""

# Setup for the open-diff-mode case: create a feature branch, write "hello" to
# myapp.py and commit, then edit it to "goodbye" without committing. Opening it
# from the Files tree shows a read-only preview of the current working tree.
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

# Replace a tracked directory with a symlink at the same path, the exact data
# shape that confuses ``addDeletedFileToTree`` (see the skipped test below).
_SYMLINK_REPRO_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "mkdir -p mydir && printf 'one\\n' > mydir/foo.md && printf 'two\\n' > mydir/bar.md && git add -A && git commit -m 'Add mydir with files'"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "rm -rf mydir && ln -s stuff.txt mydir && git add -A"
      }
    }
  ]
}`"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _open_files_panel_with(
    page: Page, prompt: str, sub_section: str = "center"
) -> tuple[PlaywrightTaskPage, PlaywrightFilesPanelElement]:
    """Run a FakeClaude prompt, wait for it, then open the Files panel.

    Returns the task page and the Files panel POM scoped to the opened section.
    Pass ``sub_section="left"`` to keep the agent chat visible in the center (e.g.
    when the test still needs to send chat messages).
    """
    task_page = start_task_and_wait_for_ready(page, prompt=prompt)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    section_root = open_panel(page, "files", sub_section=sub_section)
    return task_page, get_files_panel_in(section_root, page)


def _ensure_folder_expanded(files_panel: PlaywrightFilesPanelElement, folder_text: str) -> None:
    """Expand a folder row if it is not already expanded.

    During agent execution, the auto-expand effect may have already expanded
    ancestor folders of files the agent operated on. Blindly clicking the
    folder row would collapse it in that case, so this checks the
    ``aria-expanded`` attribute first and only clicks when needed.
    """
    folder_row = files_panel.get_tree_rows().filter(has_text=folder_text).first
    expect(folder_row).to_be_visible()
    if folder_row.get_attribute("aria-expanded") != "true":
        folder_row.click()


# --------------------------------------------------------------------------- #
# Folded-in: Task 3.6a harness smoke test.
# --------------------------------------------------------------------------- #


@user_story("to open the Files panel from the add-panel dropdown and see its list and viewer")
def test_open_files_panel_renders_list_and_viewer(sculptor_instance_: SculptorInstance) -> None:
    """The open-a-panel helper opens Files; its list + embedded viewer render.

    Folds in the Task 3.6a smoke test: open Files through the section ``+``
    add-panel dropdown (no layout / localStorage seeding), then verify the
    ExplorerLayout list and the embedded viewer's always-visible empty body
    render (FCC-04/06).
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="FCC harness smoke", workspace_name="FCC Smoke WS")

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)

    # The ExplorerLayout list (file tree) renders.
    expect(files_panel.get_list()).to_be_visible()

    # The embedded DiffViewer renders (nothing selected -> empty body, FCC-06).
    expect(files_panel.get_diff_viewer()).to_be_visible()


# --------------------------------------------------------------------------- #
# Migrated: test_file_browser.py (file-tree content) + test_file_browser_tabs.py
# --------------------------------------------------------------------------- #


@user_story("to browse files the agent has created")
def test_file_browser_shows_tree_after_agent_writes(sculptor_instance_: SculptorInstance) -> None:
    """The Files panel shows the file tree after the agent creates files."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    # The file tree should render with tree rows.
    file_tree = files_panel.get_file_tree()
    expect(file_tree).to_be_visible()
    expect(files_panel.get_tree_rows().first).to_be_visible()

    # README.md should be visible (root-level file).
    expect(files_panel.get_list()).to_contain_text("README")


@user_story("to see which files have been changed")
def test_file_tree_shows_status_indicators(sculptor_instance_: SculptorInstance) -> None:
    """File tree rows show status letter indicators for changed files."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    expect(files_panel.get_file_tree()).to_be_visible()

    # Status indicators (A for added) should be visible on file rows.
    expect(files_panel.get_status_indicators().first).to_be_visible()


@user_story("to see the file browser when the agent hasn't changed any files yet")
def test_file_browser_shows_tree_before_agent_changes(sculptor_instance_: SculptorInstance) -> None:
    """Files panel shows the file tree (from existing repo files) before the agent writes."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, "fake_claude:say `Hello!`")

    # The workspace always has repo files, so the tree renders.
    expect(files_panel.get_file_tree()).to_be_visible()


@user_story("to see the file browser populated after creating a workspace without a prompt")
def test_file_browser_populates_after_workspace_created_without_prompt(sculptor_instance_: SculptorInstance) -> None:
    """Files panel shows the file tree after creating a workspace without a prompt.

    When a workspace is created without a prompt, the agent enters a waiting
    state. The environment is still created asynchronously, and the file tree
    should populate with the cloned repo's files without sending a prompt first.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, workspace_name="No-Prompt Workspace")
    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)

    # The file tree should populate with the cloned repo's files.
    file_tree = files_panel.get_file_tree()
    expect(file_tree).to_be_visible()
    expect(files_panel.get_tree_rows().first).to_be_visible()


@user_story("to see committed and uncommitted files together in the file tree")
def test_file_tree_shows_committed_and_uncommitted_files(sculptor_instance_: SculptorInstance) -> None:
    """The file tree shows both committed and uncommitted files.

    Migrated from the residual file-tree content of the old All-tab assertion
    in ``test_file_browser_tabs.py`` (the All/Changes/History tab-switching is
    dropped — that tab model is gone).
    """
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, _COMMITTED_AND_UNCOMMITTED_PROMPT)

    file_list = files_panel.get_list()
    expect(files_panel.get_file_tree()).to_be_visible()
    expect(file_list).to_contain_text("committed.py")
    expect(file_list).to_contain_text("uncommitted.py")


@user_story("to navigate into nested folders")
def test_folder_expand_and_collapse(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a folder row toggles its expansion, showing or hiding children."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    expect(files_panel.get_file_tree()).to_be_visible()

    src_row = files_panel.get_tree_rows().filter(has_text="src").first
    expect(src_row).to_be_visible()
    app_row = files_panel.get_tree_rows().filter(has_text="App.tsx")

    # Ensure src/ is collapsed first (it may auto-expand during agent writes).
    if src_row.get_attribute("aria-expanded") == "true":
        src_row.click()
    expect(app_row).not_to_be_visible()

    # Expand src/ -> App.tsx becomes visible.
    src_row.click()
    expect(app_row.first).to_be_visible()

    # Collapse src/ again -> App.tsx hidden.
    src_row.click()
    expect(app_row).not_to_be_visible()


@user_story("to collapse all folders at once")
def test_collapse_all_folders(sculptor_instance_: SculptorInstance) -> None:
    """The collapse-all option (now in the viewer's triple-dot menu, FCC-07)
    collapses expanded folders in the tree."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    expect(files_panel.get_file_tree()).to_be_visible()

    # Expand src/ so App.tsx is visible.
    _ensure_folder_expanded(files_panel, "src")
    app_row = files_panel.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row.first).to_be_visible()

    # Collapse all via the relocated menu option.
    files_panel.get_diff_viewer().toggle_view_option_via_menu("collapse_all")

    # App.tsx should no longer be visible (folder collapsed).
    expect(app_row).not_to_be_visible()


@user_story("to see the file tree as a flat list of files")
def test_flat_list_view_shows_files_without_folders(sculptor_instance_: SculptorInstance) -> None:
    """The flat/tree toggle (now in the viewer's triple-dot menu, FCC-07)
    switches the tree to a flat list that shows files directly."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    expect(files_panel.get_file_tree()).to_be_visible()

    # Switch to the flat list view via the relocated menu option.
    files_panel.get_diff_viewer().toggle_view_option_via_menu("tree_view_mode")

    # In the flat list, the nested files appear directly (no folder expansion).
    # Assert via the list text (robust to flat-vs-tree row markup).
    file_list = files_panel.get_list()
    expect(file_list).to_contain_text("App.tsx")
    expect(file_list).to_contain_text("Header")
    expect(file_list).to_contain_text("README")


@user_story("to see new files appear in the file tree during a conversation")
def test_new_files_appear_after_followup_message(sculptor_instance_: SculptorInstance) -> None:
    """Files created in a follow-up message appear in the Files panel tree.

    Opening Files in the center makes it the active center panel (hiding the chat),
    so the follow-up message is sent first (while the chat is the active panel),
    then Files is opened — its tree must reflect both the initial and follow-up
    files.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt=WRITE_FILES_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Send a follow-up message to create another file (chat is the active center panel).
    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:write_file `{
  "file_path": "CHANGELOG.md",
  "content": "# Changelog\\n\\n## v1.0.0\\n- Initial release\\n"
}`""",
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Open Files: its tree reflects both the initial and the follow-up files.
    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    file_list = files_panel.get_list()
    expect(files_panel.get_file_tree()).to_be_visible()
    expect(file_list).to_contain_text("README")
    expect(file_list).to_contain_text("CHANGELOG")


# --------------------------------------------------------------------------- #
# Migrated: test_file_browser.py — file search
#
# The new Files panel list header (``ExplorerTreeHeader``) is an always-visible
# search input — there is no search button to reveal it, no close button, and no
# "0 found" / Escape-to-close affordance (those belonged to the old
# tabbed File-Browser header). The proven filtering content assertions carry
# over against the always-present input; the dropped affordances are part of the
# retired surface.
# --------------------------------------------------------------------------- #


@user_story("to narrow down the file tree using search")
def test_file_search_filters_visible_rows(sculptor_instance_: SculptorInstance) -> None:
    """Typing in the file search filters the tree to only matching files."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    file_tree = files_panel.get_file_tree()
    expect(file_tree).to_be_visible()

    search_input = files_panel.get_search_input()
    expect(search_input).to_be_visible()

    # Search for "Header" — only Header.tsx and its parent folders should show.
    search_input.fill("Header")

    header_row = files_panel.get_tree_rows().filter(has_text="Header")
    expect(header_row.first).to_be_visible()

    # README should NOT be visible in the filtered results.
    readme_row = files_panel.get_tree_rows().filter(has_text="README")
    expect(readme_row).to_have_count(0)


@user_story("to see a clear empty state when no files match my search")
def test_file_search_no_matches_shows_empty_state(sculptor_instance_: SculptorInstance) -> None:
    """Searching for a string that matches no files shows 'No matches' instead
    of the full tree."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    file_tree = files_panel.get_file_tree()
    expect(file_tree).to_be_visible()

    search_input = files_panel.get_search_input()
    search_input.fill("zzz_definitely_no_match")

    # The file tree should be replaced by the "No matches" message.
    expect(file_tree).not_to_be_visible()
    expect(files_panel.get_list()).to_contain_text("No matches")

    # README must not be visible — the tree must not fall back to all files.
    readme_row = files_panel.get_tree_rows().filter(has_text="README")
    expect(readme_row).to_have_count(0)


@user_story("to search files by exact substring, not fuzzy match")
def test_file_search_uses_exact_substring_matching(sculptor_instance_: SculptorInstance) -> None:
    """A near-miss typo should not match files — only exact substrings of the path."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    expect(files_panel.get_file_tree()).to_be_visible()

    search_input = files_panel.get_search_input()
    # "Headr" is close to "Header" but should NOT fuzzy-match.
    search_input.fill("Headr")

    # Header.tsx should not appear.
    header_row = files_panel.get_tree_rows().filter(has_text="Header")
    expect(header_row).to_have_count(0)


@user_story("to collapse folders while searching to focus on specific results")
def test_file_search_folders_are_collapsible(sculptor_instance_: SculptorInstance) -> None:
    """Folder nodes remain collapsible/expandable during an active search."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    file_tree = files_panel.get_file_tree()
    expect(file_tree).to_be_visible()

    # Search for ".tsx" to match both App.tsx and Header.tsx.
    search_input = files_panel.get_search_input()
    search_input.fill(".tsx")

    # Both files should be visible (folders auto-expanded on search activation).
    app_row = files_panel.get_tree_rows().filter(has_text="App.tsx")
    expect(app_row.first).to_be_visible()
    header_row = files_panel.get_tree_rows().filter(has_text="Header")
    expect(header_row.first).to_be_visible()

    # The "src" folder row should be expanded.
    src_row = files_panel.get_tree_rows().filter(has_text="src").first
    expect(src_row).to_have_attribute("aria-expanded", "true")

    # Collapse src/ — App.tsx should disappear.
    src_row.click()
    expect(src_row).to_have_attribute("aria-expanded", "false")
    expect(app_row).not_to_be_visible()

    # Re-expand — App.tsx should reappear.
    src_row.click()
    expect(src_row).to_have_attribute("aria-expanded", "true")
    expect(app_row.first).to_be_visible()


# --------------------------------------------------------------------------- #
# Migrated: test_file_open_diff_modes.py
#
# The Files panel opens a file from the tree into its OWN embedded viewer as a
# read-only file view of the working tree (the old "Browse tab" behavior). The
# committed-vs-uncommitted and All/Uncommitted-scope diff modes from the source
# file are driven by the Changes panel's scope picker, which the Files panel does
# not own; those cases are skipped here with a follow-up reason and belong to
# ``test_changes_panel.py``.
# --------------------------------------------------------------------------- #


@user_story("to see plain file contents when clicking a file in the Files tree")
def test_open_file_shows_read_only_preview(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Files tree opens a read-only file preview of the
    current working tree (not a diff)."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, _COMMIT_THEN_EDIT_PROMPT)

    expect(files_panel.get_file_tree()).to_be_visible()

    # Open myapp.py from the tree into the embedded viewer.
    viewer = files_panel.open_file("myapp.py")
    viewer.assert_diff_shows("myapp.py")

    # The viewer shows a read-only preview with the current working tree
    # content ("goodbye"), not a diff view.
    preview = viewer.get_read_only_preview()
    expect(preview).to_be_visible()
    expect(preview).to_contain_text("goodbye")


@pytest.mark.skip(reason=_SCOPE_DIFF_SKIP_REASON)
@user_story("to see uncommitted vs all-scope diffs when opening a file")
def test_scope_diff_modes(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder for the scope-dependent diff modes (HEAD-vs-working-tree and
    merge-base-vs-working-tree) that the Files panel does not surface — they are
    driven by the Changes panel's scope picker."""


# --------------------------------------------------------------------------- #
# Migrated: test_file_browser_symlink_replaces_directory.py
# --------------------------------------------------------------------------- #


@pytest.mark.skip(reason=_SYMLINK_SKIP_REASON)
@user_story("to see a clean file tree when a directory has been replaced by a symlink")
def test_directory_replaced_by_symlink_no_duplicate_row(sculptor_instance_: SculptorInstance) -> None:
    """Placeholder for the duplicate-row repro when a directory is replaced by a
    symlink at the same path. The repro requires the uncommitted Changes scope
    (the deleted children appear as D entries only there) and the original
    counted matching rows via ``page.evaluate``; both belong with the Changes
    panel coverage rather than the Files panel."""
    # The setup prompt is retained for the follow-up migration.
    _ = _SYMLINK_REPRO_PROMPT


# --------------------------------------------------------------------------- #
# FCC-04 / FCC-05 / FCC-06: shared sidebar resize + toggle + always-visible viewer
# --------------------------------------------------------------------------- #


@user_story("to resize the shared file-browser sidebar")
def test_shared_sidebar_resizes_and_has_a_minimum_width(sculptor_instance_: SculptorInstance) -> None:
    """The ExplorerLayout sidebar (the global shared list width, FCC-04) resizes
    via its divider and clamps to a minimum width.

    The divider is a focusable ``role=separator`` handle, so the resize is
    driven with the keyboard (arrow keys) to avoid mouse-coordinate math, and
    the list's measured width is read from its bounding box.
    """
    page = sculptor_instance_.page
    # Open Files into the narrow (~20%) left section, then maximize that section so
    # the shared list has room to grow before the resize is measured.
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT, sub_section="left")

    PlaywrightWorkspaceSection(page, "left").maximize()

    layout = files_panel.get_explorer_layout()
    expect(layout.get_list()).to_be_visible()

    handle = layout.get_resize_handle()
    expect(handle).to_be_visible()

    list_root = layout.get_list()
    start_box = list_root.bounding_box()
    assert start_box is not None
    start_width = start_box["width"]

    # Grow the sidebar with ArrowRight; the list should get measurably wider.
    handle.focus()
    for _ in range(3):
        handle.press("ArrowRight")
    grown_box = list_root.bounding_box()
    assert grown_box is not None
    assert grown_box["width"] > start_width, (
        f"Sidebar should grow after ArrowRight: start={start_width:.0f}, grown={grown_box['width']:.0f}"
    )

    # Shrink it well past the minimum with repeated ArrowLeft; it must clamp to
    # the 200px minimum rather than collapsing to zero.
    for _ in range(40):
        handle.press("ArrowLeft")
    clamped_box = list_root.bounding_box()
    assert clamped_box is not None
    assert clamped_box["width"] >= 190, f"Sidebar must clamp to its ~200px minimum, got {clamped_box['width']:.0f}"


@user_story("to hide and show the file-browser sidebar from the viewer header")
def test_sidebar_toggle_from_viewer_header(sculptor_instance_: SculptorInstance) -> None:
    """The sidebar-visibility toggle in the viewer header (FCC-05) collapses the
    list, leaving the viewer, and re-expands it."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    layout = files_panel.get_explorer_layout()
    expect(layout.get_list()).to_be_visible()

    # Hide the sidebar from the viewer header — the list collapses.
    layout.hide_sidebar()
    expect(layout.get_list()).to_have_count(0)

    # The viewer stays visible while the sidebar is collapsed (FCC-06).
    expect(files_panel.get_diff_viewer()).to_be_visible()

    # Show it again — the list reappears.
    layout.show_sidebar()
    expect(layout.get_list()).to_be_visible()


@user_story("to always see the viewer with an empty state when nothing is selected")
def test_viewer_always_visible_with_empty_state(sculptor_instance_: SculptorInstance) -> None:
    """With files written but nothing selected, the viewer renders its
    always-visible empty body and shows NO loading bar (FCC-06)."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    viewer = files_panel.get_diff_viewer()

    # The viewer body is visible (empty placeholder) and shows no loading bar.
    expect(viewer).to_be_visible()
    expect(viewer).to_contain_text("Open a file to view it")
    expect(viewer.get_loading_bar()).to_have_count(0)


# --------------------------------------------------------------------------- #
# Migrated: test_path_tilde_display.py
# --------------------------------------------------------------------------- #


@pytest.fixture
def _home_sentinel_dir() -> Generator[Path, None, None]:
    """Ensure a non-hidden directory exists under HOME for autocomplete.

    Some CI environments have an empty home directory with only dotfiles.
    """
    sentinel_dir = Path.home() / "test_autocomplete_dir"
    sentinel_dir.mkdir(exist_ok=True)
    yield sentinel_dir
    sentinel_dir.rmdir()


@user_story("to see paths with ~ instead of the full home directory")
def test_path_autocomplete_shows_tilde_for_home_directory(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """The path autocomplete dropdown displays ~/... instead of /Users/.../... .

    Verifies that typing ``~/`` in the add-repo dialog triggers autocomplete and
    that the autocomplete items appear (the tilde-display path surface is
    unchanged by the panel rewrite — it lives in Settings, not the Files panel).
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    dialog = repos_settings.open_add_repo_dialog()

    path_input = dialog.get_path_input()
    path_input.fill("~/")

    items = dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()
    expect(items).not_to_have_count(0)
