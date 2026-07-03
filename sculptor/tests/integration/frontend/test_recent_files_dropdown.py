"""Integration tests for the viewer header's recently-viewed-files dropdown.

The file-path breadcrumb in the Files / Changes / Commits viewer headers is a
dropdown listing recently viewed files. Each panel keeps its OWN independent
list — files viewed in the Changes panel must not appear in the Files panel's
dropdown (and vice versa) — and picking an entry stays in the originating
panel: Files re-opens a read-only file view, Changes re-opens the file's diff,
and Commits re-opens the file's diff within the commit it was viewed in.

The three panels are seeded into the (collapsed) left section, so the tests
drive them by expanding that section and switching its panel tabs (via
``open_panel``, which reveals a seeded panel where it lives).
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.changes_panel import get_changes_panel_in
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.commits_panel import PlaywrightCommitsPanelElement
from sculptor.testing.elements.commits_panel import get_commits_panel_in
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# One commit adding guide.md + util.py on a feature branch, then an uncommitted
# edit to util.py. This yields, in one workspace:
#   * Files panel: both files openable as read-only views of the working tree
#   * Changes panel: util.py as a changed file (uncommitted edit)
#   * Commits panel: the "Add guide and util" commit containing both files
_RECENTS_SETUP_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {"command": "git checkout -b feature"}
    },
    {
      "command": "write_file",
      "args": {"file_path": "guide.md", "content": "# Guide\\n\\nSome prose.\\n"}
    },
    {
      "command": "write_file",
      "args": {"file_path": "util.py", "content": "def util():\\n    return 1\\n"}
    },
    {
      "command": "bash",
      "args": {"command": "git add -A && git commit -m 'Add guide and util'"}
    },
    {
      "command": "edit_file",
      "args": {"file_path": "util.py", "old_string": "return 1", "new_string": "return 2"}
    }
  ]
}`"""


def _start_workspace_with_setup(page: Page, workspace_name: str) -> None:
    """Create a workspace and wait for the recents setup prompt to finish."""
    task_page = start_task_and_wait_for_ready(page, prompt=_RECENTS_SETUP_PROMPT, workspace_name=workspace_name)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)


def _open_commit_file(commits_panel: PlaywrightCommitsPanelElement, file_name: str) -> None:
    """Open ``file_name``'s commit-scoped diff from the (already expanded)
    first commit."""
    first_commit = commits_panel.get_commit_entries().first
    file_row = commits_panel.get_tree_rows(first_commit).filter(has_text=file_name)
    expect(file_row).to_be_visible()
    file_row.click()
    commits_panel.get_diff_viewer().assert_diff_shows(file_name)


@user_story("to see only files I viewed in this panel in its recent-files dropdown")
def test_recent_files_are_independent_per_panel(sculptor_instance_: SculptorInstance) -> None:
    """Files viewed in one panel must not appear in another panel's dropdown."""
    page = sculptor_instance_.page
    _start_workspace_with_setup(page, "Recents Per Panel WS")

    # View guide.md in the Files panel (a read-only file view).
    section_root = open_panel(page, "files")
    files_panel = get_files_panel_in(section_root, page)
    files_viewer = files_panel.open_file("guide.md")
    files_viewer.assert_diff_shows("guide.md")

    # View util.py's diff in the Changes panel.
    open_panel(page, "changes")
    changes_panel = get_changes_panel_in(section_root, page)
    changes_viewer = changes_panel.open_file("util.py")
    changes_viewer.assert_diff_shows("util.py")

    # The Changes dropdown lists util.py but NOT the file viewed in Files.
    changes_viewer.open_recent_files_dropdown()
    options = changes_viewer.get_recent_file_options()
    expect(options.filter(has_text="util.py")).to_have_count(1)
    expect(options.filter(has_text="guide.md")).to_have_count(0)
    changes_viewer.close_recent_files_dropdown()

    # Back in the Files panel, its dropdown lists guide.md but NOT the file
    # viewed in Changes. The file is re-opened first so the header (and its
    # dropdown trigger) is showing regardless of what the tab switch reset.
    open_panel(page, "files")
    files_viewer = files_panel.open_file("guide.md")
    files_viewer.assert_diff_shows("guide.md")
    files_viewer.open_recent_files_dropdown()
    options = files_viewer.get_recent_file_options()
    expect(options.filter(has_text="guide.md")).to_have_count(1)
    expect(options.filter(has_text="util.py")).to_have_count(0)
    files_viewer.close_recent_files_dropdown()


@user_story("to re-open a commit file from the Commits panel's recent-files dropdown")
def test_commits_dropdown_reopens_commit_diff_in_panel(sculptor_instance_: SculptorInstance) -> None:
    """Picking a Commits recent stays in the Commits panel and shows the
    file's diff within the commit it was viewed in."""
    page = sculptor_instance_.page
    _start_workspace_with_setup(page, "Recents Commits WS")

    section_root = open_panel(page, "commits")
    commits_panel = get_commits_panel_in(section_root, page)
    expect(commits_panel.get_list()).to_be_visible()

    # Expand the commit, then view util.py and guide.md inside it — both
    # become recents.
    first_commit = commits_panel.get_commit_entries().first
    commits_panel.get_commit_message(first_commit).click()
    _open_commit_file(commits_panel, "util.py")
    _open_commit_file(commits_panel, "guide.md")

    # Pick util.py from the dropdown: the Commits panel must stay active and
    # show util.py's COMMIT diff — the committed content ("return 1"), not the
    # uncommitted working-tree edit ("return 2").
    viewer = commits_panel.get_diff_viewer()
    viewer.select_recent_file("util.py")

    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("commits")).to_have_attribute("aria-selected", "true")
    viewer.assert_diff_shows("util.py")
    expect(viewer.get_unified_diff_views().first).to_be_visible()
    expect(viewer).to_contain_text("return 1")
    # The commit-scoped diff carries only the committed content, so the
    # uncommitted working-tree edit must be absent — a working-tree diff would
    # also render "return 1", so its presence alone can't distinguish the two.
    expect(viewer).not_to_contain_text("return 2")


@user_story("to re-open a file's diff from the Changes panel's recent-files dropdown")
def test_changes_dropdown_reopens_diff_in_panel(sculptor_instance_: SculptorInstance) -> None:
    """Picking a Changes recent stays in the Changes panel and re-opens the
    diff the user previously viewed — including for a committed-only file
    viewed under the "All" (vs-target-branch) scope, which must not degrade
    to a read-only file view."""
    page = sculptor_instance_.page
    _start_workspace_with_setup(page, "Recents Changes WS")

    section_root = open_panel(page, "changes")
    changes_panel = get_changes_panel_in(section_root, page)

    # Under the default "All" scope, view guide.md (committed-only — it has no
    # uncommitted changes) and then util.py, so guide.md is a non-current recent.
    changes_panel.open_file("guide.md").assert_diff_shows("guide.md")
    viewer = changes_panel.open_file("util.py")
    viewer.assert_diff_shows("util.py")

    # Pick guide.md from the dropdown: the Changes panel must stay active and
    # show guide.md's diff again — its committed content as added lines — not
    # a read-only preview.
    viewer.select_recent_file("guide.md")

    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("changes")).to_have_attribute("aria-selected", "true")
    viewer.assert_diff_shows("guide.md")
    expect(viewer.get_unified_diff_views().first).to_be_visible()
    expect(viewer).to_contain_text("# Guide")


@user_story("to switch between recently viewed files within the Files panel")
def test_files_dropdown_switches_file_within_panel(sculptor_instance_: SculptorInstance) -> None:
    """Picking a Files recent stays in the Files panel as a read-only file
    view of the working tree — even for a file that has uncommitted changes
    (it must not bounce to the Changes panel as a diff)."""
    page = sculptor_instance_.page
    _start_workspace_with_setup(page, "Recents Files Switch WS")

    section_root = open_panel(page, "files")
    files_panel = get_files_panel_in(section_root, page)

    # View util.py (which has an uncommitted edit), then guide.md.
    files_panel.open_file("util.py").assert_diff_shows("util.py")
    viewer = files_panel.open_file("guide.md")
    viewer.assert_diff_shows("guide.md")

    # Pick util.py from the dropdown: the Files panel must stay active and show
    # util.py as a read-only preview of the working tree ("return 2"), not
    # bounce to the Changes panel with a diff.
    viewer.select_recent_file("util.py")

    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_panel_tab("files")).to_have_attribute("aria-selected", "true")
    viewer.assert_diff_shows("util.py")
    preview = viewer.get_read_only_preview()
    expect(preview).to_be_visible()
    expect(preview).to_contain_text("return 2")
