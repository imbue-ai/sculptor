"""Integration tests for the Files panel — the workspace file tree paired with
its own embedded DiffViewer.

The Files panel is one of three separate panels (Files, Changes, Commits) that
each pair a list with an always-visible embedded viewer via the shared
``ExplorerLayout``. There is no tab model within a panel: Changes and Commits
are their own panels, so there is no ``FILE_BROWSER_TAB_*`` surface.

The panel is opened through the section ``+`` add-panel dropdown (the shared
``open_panel`` helper) rather than being a default docked panel, and the file
tree, search box, status indicators, and embedded viewer are driven through the
``PlaywrightFilesPanelElement`` / ``ExplorerLayout`` / ``DiffViewer`` POMs
scoped to the opened section. The list view controls (flat/tree, collapse-all)
live under the viewer header's single triple-dot menu, reached via
``toggle_view_option_via_menu``; the sidebar-visibility toggle also lives in the
viewer header, and the viewer is always visible with an empty body when nothing
is selected.

The scope picker (All/Uncommitted), Review All, copy-path, Cmd+W tab close, and
the committed-vs-uncommitted diff modes are not part of the Files panel surface:
they belong to the Changes / Commits panels and are covered by
``test_changes_panel.py`` / ``test_diff_viewer.py``. The diff-mode assertions
that depend on the scope picker (and the symlink-replaces-directory repro, which
needs the uncommitted Changes scope) live in ``test_changes_panel.py``, since
the Files panel does not own that surface.
"""

import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.changes_panel import get_changes_panel_in
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.files_panel import PlaywrightFilesPanelElement
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# --------------------------------------------------------------------------- #
# FakeClaude prompts.
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

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _open_files_panel_with(
    page: Page, prompt: str, sub_section: str = "center", workspace_name: str | None = None
) -> tuple[PlaywrightTaskPage, PlaywrightFilesPanelElement]:
    """Run a FakeClaude prompt, wait for it, then open the Files panel.

    Returns the task page and the Files panel POM scoped to the section that
    actually hosts the panel. Files is a seeded panel living in the LEFT
    section, and ``open_panel`` reveals a seeded panel where it lives for both
    ``sub_section="center"`` (the default) and ``"left"`` — it never moves one
    to center — so callers must scope panel/layout POMs to the returned POM
    rather than assuming a section. ``workspace_name`` names the created
    workspace so a test can navigate back to it later.
    """
    task_page = start_task_and_wait_for_ready(page, prompt=prompt, workspace_name=workspace_name)
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
# Harness smoke test.
# --------------------------------------------------------------------------- #


@user_story("to open the Files panel from the add-panel dropdown and see its list and viewer")
def test_open_files_panel_renders_list_and_viewer(sculptor_instance_: SculptorInstance) -> None:
    """The open-a-panel helper opens Files; its list + embedded viewer render.

    Opens Files through the section ``+`` add-panel dropdown (no layout /
    localStorage seeding), then verifies the ExplorerLayout list and the
    embedded viewer's always-visible empty body render.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="FCC harness smoke", workspace_name="FCC Smoke WS")

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)

    # The ExplorerLayout list (file tree) renders.
    expect(files_panel.get_list()).to_be_visible()

    # The embedded DiffViewer renders (nothing selected -> empty body).
    expect(files_panel.get_diff_viewer()).to_be_visible()


# --------------------------------------------------------------------------- #
# File-tree content
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
    """The file tree shows both committed and uncommitted files."""
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
    """The collapse-all option in the viewer's triple-dot menu collapses
    expanded folders in the tree."""
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
    """The flat/tree toggle in the viewer's triple-dot menu switches the tree
    to a flat list that shows files directly."""
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
# File search
#
# The Files panel list header (``ExplorerTreeHeader``) is an always-visible
# search input: there is no search button to reveal it, no close button, and no
# "0 found" / Escape-to-close affordance. The filtering assertions run against
# that always-present input.
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
    header_row = files_panel.get_tree_rows().filter(has_text="Header")

    # An exact substring ("Header") matches and auto-expands its parent folders,
    # so the row surfaces — proving the filter engaged before the near-miss check.
    search_input.fill("Header")
    expect(header_row.first).to_be_visible()

    # "Headr" is a near-miss typo and must NOT fuzzy-match, so the row drops out.
    search_input.fill("Headr")
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


@user_story("to return to a workspace and find the file tree collapsed the way I left it")
def test_reentry_preserves_file_tree_collapse(sculptor_instance_: SculptorInstance) -> None:
    """Re-entering a workspace keeps a folder the user collapsed collapsed.

    The Files tree auto-expands ancestors of files an agent is actively writing,
    but once the agent is idle that must not re-expand a folder the user chose to
    collapse when the panel remounts on a workspace switch. (Persisting a collapse
    also proves expansion state survives, since both directions share one atom.)
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(page, prompt=WRITE_FILES_PROMPT, workspace_name="File Collapse A")
    wait_for_completed_message_count(chat_panel=task_page.get_chat_panel(), expected_message_count=2)

    # Collapse src/ (it auto-expands while the agent writes into it). Open the panel in
    # the left section it is seeded into — opening it against the center leaves the
    # add-panel dropdown's overlay lingering, which then intercepts the next dialog.
    files_panel = get_files_panel_in(open_panel(page, "files", sub_section="left"), page)
    _ensure_folder_expanded(files_panel, "src")
    src_row = files_panel.get_tree_rows().filter(has_text="src").first
    src_row.click()
    expect(src_row).to_have_attribute("aria-expanded", "false")

    # Switch to a second workspace, then return to A.
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="File Collapse B")
    navigate_to_workspace(page, "File Collapse A")
    expect(task_page.get_chat_panel()).to_be_visible(timeout=60_000)

    # Reveal the Files panel and confirm src/ is still collapsed.
    files_panel = get_files_panel_in(open_panel(page, "files", sub_section="left"), page)
    src_row = files_panel.get_tree_rows().filter(has_text="src").first
    expect(src_row).to_have_attribute("aria-expanded", "false")


# --------------------------------------------------------------------------- #
# Opening a file into the embedded viewer
#
# The Files panel opens a file from the tree into its own embedded viewer as a
# read-only file view of the working tree. The committed-vs-uncommitted and
# All/Uncommitted-scope diff modes are driven by the Changes panel's scope
# picker, which the Files panel does not own; those cases live in
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


# --------------------------------------------------------------------------- #
# Resizable shared-width sidebar + visibility toggle + always-visible viewer
# --------------------------------------------------------------------------- #


@user_story("to widen the file-browser list by dragging its divider and see the same width in the Changes panel")
def test_list_divider_drag_resizes_and_width_is_shared_across_panels(sculptor_instance_: SculptorInstance) -> None:
    """Dragging the ExplorerLayout divider widens the list pane, and
    the new width carries over when the Changes panel becomes the section's
    active tab — the width is one shared, persisted value across the Files /
    Changes / Commits panels rather than per-panel state.

    The Files / Changes panels stay in their seeded LEFT section (``open_panel``
    reveals a seeded panel where it lives; it never moves one to center). That
    section's ~20% default width is narrower than the list's default width plus
    the drag growth, so the section is widened first via its keyboard-drivable
    border to give the drag explicit headroom — otherwise the divider would be
    pushed past the section edge and clipped by the section's overflow. Width
    changes are asserted coarsely (direction of change, then equality within a
    small tolerance), not exact-pixel, to avoid layout-math flakiness.
    """
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    # Scope the layout to the section root that actually hosts the panel (the
    # seeded left section) via the returned POM, never a hard-coded section.
    layout = files_panel.get_explorer_layout()
    expect(layout.get_list()).to_be_visible()
    expect(layout.get_resize_handle()).to_be_visible()

    # Widen the left section before dragging: keyboard steps on its border
    # (each ~10% of the grid) take it from its ~20% default to comfortably
    # above list-default + drag growth, and the poll waits for the widened
    # section to actually render before anything is measured.
    section_handle = PlaywrightWorkspaceSection(page, "left").get_resize_handle()
    expect(section_handle).to_be_visible()
    section_handle.focus()
    for _ in range(3):
        section_handle.press("ArrowRight")
    page.wait_for_function(
        """(testId) => {
            const el = document.querySelector(`[data-testid="${testId}"]`);
            return el && el.getBoundingClientRect().width >= 450;
        }""",
        arg=str(ElementIDs.SECTION_LEFT),
    )

    start_width = layout.get_list_width_px()
    layout.drag_resize_handle_by(80)

    # Poll rather than measure once: the drag writes the width synchronously,
    # but a busy renderer can commit the resulting layout a beat later.
    grown_width = layout.wait_for_list_width_above(start_width + 40)

    # Open Changes as the section's active tab: its list renders at the SAME
    # shared width the drag just set. Gate on the Changes list itself (not the
    # divider, which the outgoing Files layout also renders) so the width is
    # measured on the mounted Changes panel.
    changes_root = open_panel(page, "changes", sub_section="left")
    changes_panel = get_changes_panel_in(changes_root, page)
    expect(changes_panel.get_list()).to_be_visible()
    expect(layout.get_resize_handle()).to_be_visible()

    # Poll for the shared width to land rather than measuring once: the Changes
    # list can mount a beat before it reads back the persisted width under load.
    changes_width = layout.wait_for_list_width_above(grown_width - 2)
    assert changes_width <= grown_width + 2, (
        f"Changes list must reuse the shared width: files={grown_width:.0f}, changes={changes_width:.0f}"
    )


@user_story("to hide and show the file-browser sidebar from the viewer header")
def test_sidebar_toggle_from_viewer_header(sculptor_instance_: SculptorInstance) -> None:
    """The sidebar-visibility toggle in the viewer header collapses the
    list, leaving the viewer, and re-expands it."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    layout = files_panel.get_explorer_layout()
    expect(layout.get_list()).to_be_visible()

    # Hide the sidebar from the viewer header — the list collapses.
    layout.hide_sidebar()
    expect(layout.get_list()).to_have_count(0)

    # The viewer stays visible while the sidebar is collapsed.
    expect(files_panel.get_diff_viewer()).to_be_visible()

    # Show it again — the list reappears.
    layout.show_sidebar()
    expect(layout.get_list()).to_be_visible()


@user_story("to return to a workspace and find the file-browser sidebar hidden the way I left it")
def test_reentry_preserves_hidden_sidebar(sculptor_instance_: SculptorInstance) -> None:
    """Hiding the Explorer sidebar stays hidden across a workspace switch.

    The sidebar-visibility toggle is persisted per panel, so remounting the
    panel on a workspace switch must not reopen a sidebar the user hid.
    """
    page = sculptor_instance_.page
    task_page, files_panel = _open_files_panel_with(
        page, WRITE_FILES_PROMPT, sub_section="left", workspace_name="Sidebar Hide A"
    )
    layout = files_panel.get_explorer_layout()
    expect(layout.get_list()).to_be_visible()
    layout.hide_sidebar()
    expect(layout.get_list()).to_have_count(0)

    # Switch to a second workspace, then return to A.
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Sidebar Hide B")
    navigate_to_workspace(page, "Sidebar Hide A")
    expect(task_page.get_chat_panel()).to_be_visible(timeout=60_000)

    # Reveal the Files panel and confirm the sidebar is still hidden.
    files_panel = get_files_panel_in(open_panel(page, "files", sub_section="left"), page)
    expect(files_panel.get_explorer_layout().get_list()).to_have_count(0)


@user_story("to always see the viewer with an empty state when nothing is selected")
def test_viewer_always_visible_with_empty_state(sculptor_instance_: SculptorInstance) -> None:
    """With files written but nothing selected, the viewer renders its
    always-visible empty body and shows NO loading bar."""
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    viewer = files_panel.get_diff_viewer()

    # The viewer body is visible (empty placeholder) and shows no loading bar.
    expect(viewer).to_be_visible()
    expect(viewer).to_contain_text("Open a file to view it")
    expect(viewer.get_loading_bar()).to_have_count(0)


@user_story("to keep the file I opened in the Files panel after maximizing and restoring its section")
def test_open_file_survives_section_maximize_restore(sculptor_instance_: SculptorInstance) -> None:
    """Maximize/restore remounts the panel; the open file must survive it.

    The Files panel's clicked-file selection must be held per-workspace (like
    the Changes panel's) rather than in component state, so the remount that a
    section maximize/restore causes does not silently reset the viewer to its
    empty state while the user is looking at a file.
    """
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT)

    viewer = files_panel.open_file("README.md")
    viewer.assert_diff_shows("README.md")
    expect(viewer.get_read_only_preview()).to_be_visible()

    # The Files panel lives in the left section (seeded); maximize + restore it.
    # While maximized the section-root testid is not rendered (the maximized
    # branch mounts the PanelSection directly), so the viewer is re-asserted
    # after restore — the remount round-trip is what loses component state.
    left = PlaywrightWorkspaceSection(page, "left")
    left.maximize()
    left.restore()

    viewer.assert_diff_shows("README.md")
    expect(viewer.get_read_only_preview()).to_be_visible()


@user_story("to keep the file I opened in the Files panel after visiting another panel tab")
def test_open_file_survives_panel_tab_switch(sculptor_instance_: SculptorInstance) -> None:
    """Switching the section's active tab away and back must keep the open file.

    The Files panel unmounts entirely while a sibling tab (here Changes) is the
    section's active panel, so its clicked-file selection must be held
    per-workspace rather than in component state — otherwise returning to the
    Files tab silently resets the viewer to its empty state.
    """
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(page, WRITE_FILES_PROMPT, sub_section="left")

    viewer = files_panel.open_file("README.md")
    viewer.assert_diff_shows("README.md")
    expect(viewer.get_read_only_preview()).to_be_visible()

    # Activate the sibling Changes tab: the Files panel (and its file-tree list)
    # unmounts.
    left = PlaywrightWorkspaceSection(page, "left")
    left.get_panel_tab("changes").click()
    expect(files_panel.get_list()).to_have_count(0)

    # Back to Files: the same file is still open in the embedded viewer.
    left.get_panel_tab("files").click()
    viewer.assert_diff_shows("README.md")
    expect(viewer.get_read_only_preview()).to_be_visible()


@user_story("to find the file I had open in a workspace's Files panel when I come back to it")
def test_open_file_is_kept_per_workspace_across_workspace_switch(sculptor_instance_: SculptorInstance) -> None:
    """A workspace round-trip keeps the Files selection, with no cross-workspace leak.

    The selection is keyed per workspace: a second workspace's Files panel starts
    with no selection (the first workspace's open file must not leak into it), and
    returning to the first workspace restores its open file.
    """
    page = sculptor_instance_.page
    _, files_panel = _open_files_panel_with(
        page, WRITE_FILES_PROMPT, sub_section="left", workspace_name="Files Selection A WS"
    )

    viewer = files_panel.open_file("README.md")
    viewer.assert_diff_shows("README.md")

    # Workspace B seeds its own default layout; its Files panel has no selection.
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Files Selection B WS")
    section_root_b = open_panel(page, "files", sub_section="left")
    files_panel_b = get_files_panel_in(section_root_b, page)
    expect(files_panel_b.get_diff_viewer()).to_contain_text("Open a file to view it")

    # Back to A: its Files panel still shows the file opened before the switch.
    navigate_to_workspace(page, "Files Selection A WS")
    expect(page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible(timeout=60_000)
    left_a = PlaywrightWorkspaceSection(page, "left")
    files_panel_a = get_files_panel_in(left_a.get_section(), page)
    viewer_a = files_panel_a.get_diff_viewer()
    viewer_a.assert_diff_shows("README.md")
    expect(viewer_a.get_read_only_preview()).to_be_visible()


# --------------------------------------------------------------------------- #
# Path autocomplete tilde display
# --------------------------------------------------------------------------- #


@pytest.fixture
def _home_sentinel_dir() -> Generator[Path, None, None]:
    """Ensure a non-hidden directory exists under HOME for autocomplete.

    Some CI environments have an empty home directory with only dotfiles.
    """
    # Suffix with the pid so parallel xdist workers each get their own dir under
    # the shared real HOME, and tear down idempotently so an already-removed dir
    # does not fail teardown.
    sentinel_dir = Path.home() / f"sculptor_autocomplete_dir_{os.getpid()}"
    sentinel_dir.mkdir(exist_ok=True)
    try:
        yield sentinel_dir
    finally:
        shutil.rmtree(sentinel_dir, ignore_errors=True)


@user_story("to see paths with ~ instead of the full home directory")
def test_path_autocomplete_shows_tilde_for_home_directory(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """The path autocomplete dropdown displays ``~/…`` instead of the expanded
    home directory.

    Typing ``~/`` in the add-repo dialog (in Settings) triggers autocomplete;
    the listed entries render with a leading ``~/`` rather than the absolute
    home path.
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    dialog = repos_settings.open_add_repo_dialog()

    path_input = dialog.get_path_input()
    path_input.fill("~/")

    items = dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    # Home-directory entries render with a leading ``~/`` rather than the
    # expanded absolute home path.
    expect(items.first).to_contain_text("~/")
    expect(items.filter(has_text=str(Path.home()))).to_have_count(0)
