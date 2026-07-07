"""Integration tests for the Changes panel — the changed-file browser paired with
its own embedded DiffViewer.

The Changes panel pairs the changes browser (the scope picker All/Uncommitted,
the commit-from-changes button, the changed-file tree, and per-file discard)
with an always-visible embedded viewer via the shared ``ExplorerLayout``. There
is no tab model: the Files and Commits panels are their own panels.

The panel is opened through the section ``+`` add-panel dropdown (the shared
``open_panel`` helper). The scope picker, commit button, changed-file tree, and
discard dialog are driven through the ``PlaywrightChangesPanelElement`` POM
scoped to the section the panel lives in, and a file's diff opens into the
panel's OWN embedded viewer rather than a page-wide active diff. The discard
controls only render in the Uncommitted scope, so tests select the Uncommitted
scope through the picker before discarding.

The Changes panel is seeded into the (collapsed-by-default) left section, so
opening it reveals it there while the agent chat stays mounted in the center
section. Tests that observe a chat message after a panel action (the commit
button) read the still-mounted center chat.

The scope picker also drives the scope-dependent diff modes (HEAD-vs-working in
the Uncommitted scope, merge-base-vs-working in the All scope), the
moved/renamed-file R-status rendering, and the symlink-replaces-directory
uncommitted-scope repro (whose duplicated same-path rows carry no distinguishing
testid, so the row names are counted via a locator ``evaluate_all`` — a budgeted
exception to the ``no-integration-page-evaluate`` rule).
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.changes_panel import PlaywrightChangesPanelElement
from sculptor.testing.elements.changes_panel import get_changes_panel_in
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_viewer import ensure_unified_view
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# --------------------------------------------------------------------------- #
# FakeClaude prompts
# --------------------------------------------------------------------------- #

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""

# Writes an uncommitted nested tree so the Changes tree shows a "src" folder row
# with a nested "components" folder — enough depth to collapse a folder.
_NESTED_CHANGES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "src/App.tsx",
        "content": "export const App = () => null;\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "src/components/Header.tsx",
        "content": "export const Header = () => null;\\n"
      }
    }
  ]
}`"""

# Create a feature branch, write+commit app.py, then edit it without committing,
# so the uncommitted diff is a modification (hello -> goodbye) rather than a full
# add from the base branch.
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

# Commit alpha.py + beta.py on a feature branch, then edit alpha.py only, so the
# Uncommitted scope shows only alpha.py while the All scope shows both files.
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

# Write done.py and commit it immediately, so nothing remains uncommitted.
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

# Write+commit counter.py, then edit it (so it shows as M uncommitted). A
# follow-up commit prompt then clears the remaining change.
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

# Feature branch: commit a 5-line file, then modify one line, so the uncommitted
# header stats are +1/-1 (not +5/-0).
_LINE_STATS_PROMPT = """\
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

# A new file whose body contains the literal text "deleted file mode" — the
# status determination must not match diff metadata against file content.
_NEW_FILE_WITH_DELETED_FILE_MODE_CONTENT_PROMPT = """\
fake_claude:write_file `{
  "file_path": "tricky.txt",
  "content": "This file talks about deleted file mode in git diffs.\\n"
}`"""

# Commit notes.txt (and, transitively via git add -A, the already-present
# tricky.txt), then edit notes.txt so its new content mentions "deleted file
# mode"; the edited file must show M, not D.
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

# Two commits on a feature branch, then push it so the same commits exist on
# origin/feature-refresh-test; pointing the target branch there yields no diff.
_TWO_COMMITS_PLUS_PUSH_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature-refresh-test"
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
    },
    {
      "command": "bash",
      "args": {
        "command": "git push origin feature-refresh-test"
      }
    }
  ]
}`"""

# Two uncommitted files; one is discarded in the discard tests.
_WRITE_TWO_FILES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "keep.py",
        "content": "keep = True\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "discard_me.py",
        "content": "remove = True\\n"
      }
    }
  ]
}`"""

# Feature branch with one committed file (visible only in All) and one
# uncommitted file (visible in both All and Uncommitted).
_COMMITTED_PLUS_UNCOMMITTED_PROMPT = """\
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
        "file_path": "scratch.py",
        "content": "y = 2\\n"
      }
    }
  ]
}`"""

# Feature branch: write "hello" to myapp.py and commit, then edit it to
# "goodbye" without committing. The Uncommitted scope shows the HEAD->working
# tree diff (hello -> goodbye); the All scope shows the merge-base->working tree
# diff (the whole file as "goodbye", with no "hello").
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

# Step 1 commits a directory containing two files; step 2 deletes the directory,
# replaces it with a symlink at the same path (``mydir`` now points at the
# pre-existing ``stuff.txt``), and stages the result. ``git ls-files`` then
# reports ``mydir`` as a regular file while the uncommitted diff carries
# ``D mydir/foo.md`` / ``D mydir/bar.md`` — the exact data shape that makes
# ``addDeletedFileToTree`` synthesize a duplicate folder node at the file's path.
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

# Move a file that exists on main (the target branch) to a new directory without
# changing its name; the vs-target-branch diff detects this as a rename (status R).
_RENAME_FILE_PROMPT = """\
fake_claude:bash `{
  "command": "mkdir -p lib && git mv src/helpers.py lib/helpers.py && git commit -m 'Move helpers to lib'"
}`"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _open_changes_panel_with(page: Page, prompt: str) -> tuple[PlaywrightTaskPage, PlaywrightChangesPanelElement]:
    """Run a FakeClaude prompt, wait for it, then reveal the Changes panel.

    Returns the task page and the Changes panel POM scoped to the left section
    the panel is seeded into. The agent chat stays mounted in the center section,
    so assertions can read either the panel or the chat.
    """
    task_page = start_task_and_wait_for_ready(page, prompt=prompt)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    section_root = open_panel(page, "changes", sub_section="left")
    return task_page, get_changes_panel_in(section_root, page)


def _select_uncommitted_scope(changes_panel: PlaywrightChangesPanelElement) -> None:
    """Switch the scope picker to Uncommitted (the default is All)."""
    scope_uncommitted = changes_panel.get_scope_uncommitted()
    expect(scope_uncommitted).to_be_visible()
    scope_uncommitted.click()
    expect(scope_uncommitted).to_have_attribute("data-state", "on")


def _select_all_scope(changes_panel: PlaywrightChangesPanelElement) -> None:
    """Switch the scope picker to All (vs target branch)."""
    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_be_visible()
    scope_all.click()
    expect(scope_all).to_have_attribute("data-state", "on")


@user_story("to return to a workspace and find the changes tree collapsed the way I left it")
def test_reentry_preserves_changes_tree_collapse(sculptor_instance_: SculptorInstance) -> None:
    """Re-entering a workspace keeps a folder the user collapsed in the Changes tree collapsed.

    The Changes tree auto-expands every folder when it first appears, but a folder
    the user then collapses must stay collapsed across a workspace switch — the
    panel remounting must not re-expand it.
    """
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        page, prompt=_NESTED_CHANGES_PROMPT, workspace_name="Changes Tree Collapse A"
    )
    wait_for_completed_message_count(chat_panel=task_page.get_chat_panel(), expected_message_count=2)
    section_root = open_panel(page, "changes", sub_section="left")
    changes_panel = get_changes_panel_in(section_root, page)

    # src/ auto-expands when the changes tree first appears; collapse it.
    src_row = changes_panel.get_changes_tree().get_tree_rows().filter(has_text="src").first
    expect(src_row).to_have_attribute("aria-expanded", "true")
    src_row.click()
    expect(src_row).to_have_attribute("aria-expanded", "false")

    # Switch to a second workspace, then return to A.
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Changes Tree Collapse B")
    navigate_to_workspace(page, "Changes Tree Collapse A")
    expect(task_page.get_chat_panel()).to_be_visible(timeout=60_000)

    # Reveal the Changes panel and confirm src/ is still collapsed.
    section_root = open_panel(page, "changes", sub_section="left")
    changes_panel = get_changes_panel_in(section_root, page)
    src_row = changes_panel.get_changes_tree().get_tree_rows().filter(has_text="src").first
    expect(src_row).to_have_attribute("aria-expanded", "false")


@user_story("to see only uncommitted changes when clicking a file in the Changes panel")
def test_individual_file_diff_shows_only_uncommitted_changes(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a file in the Changes panel (Uncommitted scope) shows only the
    uncommitted change.

    After creating a feature branch, committing a file, then editing it again,
    the diff should show a modification (hello -> goodbye), not the entire file
    as newly added from the base branch.
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _EDIT_AFTER_COMMIT_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("app.py")

    # The status indicator in the changes tree should show "M" (modified).
    status = changes_tree.get_row_status(tree_rows.first)
    expect(status).to_have_text("M")

    # Open the file into the panel's own embedded viewer.
    viewer = changes_panel.open_file("app.py")
    ensure_unified_view(viewer)

    diff_header = viewer.get_file_header()
    expect(diff_header).to_contain_text("app.py")

    # The diff should show a modification: both 'hello' (removed) and 'goodbye'
    # (added) are visible since it's a HEAD->working tree change.
    diff_view = viewer.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    expect(diff_view).to_contain_text("hello")
    expect(diff_view).to_contain_text("goodbye")


@user_story("to see all branch files in the All scope and only uncommitted changes in the Uncommitted scope")
def test_individual_diff_matches_all_scope(sculptor_instance_: SculptorInstance) -> None:
    """The All scope shows all branch changes; the Uncommitted scope plus an
    individual file click shows only the uncommitted edit.

    After creating a feature branch, committing alpha.py and beta.py, then
    editing alpha.py: the All scope shows both alpha.py and beta.py, while the
    Uncommitted scope shows only alpha.py and clicking it shows the uncommitted
    edit. (Re-anchored from the retired Review All surface to the scope picker.)
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _COMMIT_THEN_EDIT_ONE_PROMPT)

    # All scope (the default) shows both the committed and the edited file.
    _select_all_scope(changes_panel)
    all_tree = changes_panel.get_changes_tree()
    expect(all_tree).to_be_visible()
    expect(all_tree.get_tree_rows().filter(has_text="alpha.py")).to_be_visible()
    expect(all_tree.get_tree_rows().filter(has_text="beta.py")).to_be_visible()

    # Uncommitted scope shows only alpha.py (beta.py is committed, unchanged).
    _select_uncommitted_scope(changes_panel)
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("alpha.py")

    # Clicking alpha.py shows the uncommitted change a=1 -> a=999.
    viewer = changes_panel.open_file("alpha.py")
    ensure_unified_view(viewer)
    expect(viewer.get_file_header()).to_contain_text("alpha.py")

    diff_view = viewer.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    expect(diff_view).to_contain_text("a = 1")
    expect(diff_view).to_contain_text("a = 999")


@user_story("to see the changes panel clear after committing all changes")
def test_changes_panel_empty_after_commit(sculptor_instance_: SculptorInstance) -> None:
    """After committing all changes, the Changes panel shows no files."""
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _COMMIT_ALL_PROMPT)

    _select_uncommitted_scope(changes_panel)
    expect(changes_panel.get_list()).to_contain_text("No changes")


@user_story("to see the changes panel update correctly after a second commit")
def test_changes_panel_updates_after_second_commit(sculptor_instance_: SculptorInstance) -> None:
    """The Changes panel clears after committing the remaining changes.

    Sequence: write -> commit -> edit -> (file shows as M) -> commit again.
    After the second commit, the Changes panel is empty. The follow-up commit is
    sent via the chat, and the still-mounted panel reflects the emptied tree.
    """
    page = sculptor_instance_.page
    task_page, changes_panel = _open_changes_panel_with(page, _WRITE_AND_COMMIT_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("counter.py")

    # Commit the remaining change via a follow-up chat message.
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel=chat_panel, message=_COMMIT_AGAIN_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # After the second commit the Changes panel is empty.
    _select_uncommitted_scope(changes_panel)
    expect(changes_panel.get_changes_tree().get_tree_rows()).to_have_count(0)


@user_story("to see correct line stats for uncommitted changes")
def test_diff_header_line_stats_reflect_uncommitted_only(sculptor_instance_: SculptorInstance) -> None:
    """Diff file header line stats reflect only uncommitted changes.

    After committing a 5-line file then modifying 1 line, the header should show
    +1 (the uncommitted edit), not +5 (the entire file as new from the base
    branch).
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _LINE_STATS_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)

    viewer = changes_panel.open_file("lines.py")
    diff_header = viewer.get_file_header()
    expect(diff_header).to_be_visible()
    expect(diff_header).to_contain_text("lines.py")

    # The uncommitted change is 1 line modified (+1/-1); the header shows +1.
    expect(diff_header).to_contain_text("+1")
    expect(diff_header).not_to_contain_text("+5")


@user_story("to see correct status for files whose content contains 'deleted file mode'")
def test_file_containing_deleted_file_mode_text_not_shown_as_deleted(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Files whose content contains 'deleted file mode' must not be marked deleted.

    A new file with 'deleted file mode' in its body should show 'A' (added), and
    an edited file with the same text should show 'M' (modified) — the status
    determination must not match diff metadata patterns against file content.
    """
    page = sculptor_instance_.page

    # Scenario 1: a new file whose content contains "deleted file mode".
    task_page, changes_panel = _open_changes_panel_with(page, _NEW_FILE_WITH_DELETED_FILE_MODE_CONTENT_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("tricky.txt")

    # The file is newly added — status must be "A", not "D".
    status = changes_tree.get_row_status(tree_rows.first)
    expect(status).to_have_text("A")

    # Scenario 2: an edited file whose new content contains "deleted file mode".
    # Send the follow-up via the chat.
    chat_panel = task_page.get_chat_panel()
    send_chat_message(
        chat_panel=chat_panel,
        message=_EDIT_FILE_TO_ADD_DELETED_FILE_MODE_CONTENT_PROMPT,
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # The git commit in scenario 2 committed everything (including tricky.txt),
    # leaving only the edited notes.txt uncommitted — it must show "M", not "D".
    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    notes_row = changes_tree.get_tree_rows().filter(has_text="notes.txt")
    expect(notes_row).to_be_visible()
    notes_status = changes_tree.get_row_status(notes_row)
    expect(notes_status).to_have_text("M")


@user_story("to switch diff scope and see the toggle update")
def test_scope_switch_toggles_active_scope(sculptor_instance_: SculptorInstance) -> None:
    """Switching scope updates the active scope button and the listed files.

    Start on All scope (the default), switch to Uncommitted, then switch back to
    All and verify the file is still listed.
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _WRITE_FILE_PROMPT)

    # The scope picker starts on All (the default).
    scope_picker = changes_panel.get_scope_picker()
    expect(scope_picker).to_be_visible()

    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_have_attribute("data-state", "on")

    # The file is visible in the changes tree.
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    expect(changes_tree.get_tree_rows().filter(has_text="hello.py")).to_be_visible()

    # Switch to Uncommitted scope.
    scope_uncommitted = changes_panel.get_scope_uncommitted()
    scope_uncommitted.click()
    expect(scope_uncommitted).to_have_attribute("data-state", "on")

    # Switch back to All — the file should still be listed.
    scope_all.click()
    expect(scope_all).to_have_attribute("data-state", "on")
    expect(changes_tree.get_tree_rows().filter(has_text="hello.py")).to_be_visible()


@user_story("to see the Changes panel update when the target branch is changed")
def test_changes_panel_updates_on_target_branch_change(sculptor_instance_: SculptorInstance) -> None:
    """Changing the target branch triggers a diff refresh so the All scope
    reflects the new fork-point.

    When the target branch is changed to the same branch we just pushed (same
    commits as HEAD), the All scope shows no changed files since there is no
    divergence.
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _TWO_COMMITS_PLUS_PUSH_PROMPT)

    _select_all_scope(changes_panel)

    # Initially (target = origin/main), both files are visible as changes.
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.filter(has_text="first.py")).to_be_visible()
    expect(tree_rows.filter(has_text="second.py")).to_be_visible()

    # Change the target branch to origin/feature-refresh-test (same as HEAD).
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", page.url)
    assert match, f"Could not extract workspace ID from URL: {page.url}"
    workspace_id = match.group(1)
    base_url = sculptor_instance_.backend_api_url.rstrip("/")
    response = page.request.patch(
        f"{base_url}/api/v1/workspaces/{workspace_id}",
        data={"target_branch": "origin/feature-refresh-test"},
    )
    assert response.ok, f"Failed to update target branch: {response.status}"

    # The Changes panel refreshes — fork-point = HEAD, so no files changed.
    expect(tree_rows.filter(has_text="first.py")).to_be_hidden()
    expect(tree_rows.filter(has_text="second.py")).to_be_hidden()


@user_story("to commit changes using the commit button in the Changes panel")
def test_commit_button_sends_commit_message(sculptor_instance_: SculptorInstance) -> None:
    """The commit button sends the commit prompt to the agent.

    After writing a file, reveal the Changes panel and select the Uncommitted
    scope so the button reflects the uncommitted change count. The button sends
    through the workspace-scoped commit action, and the agent receives the
    commit prompt.
    """
    page = sculptor_instance_.page
    task_page, changes_panel = _open_changes_panel_with(page, _WRITE_FILE_PROMPT)

    # Commit only applies to uncommitted changes; the button count tracks them.
    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("hello.py")

    # The button is enabled whenever there is an uncommitted change to commit.
    commit_btn = changes_panel.get_commit_button()
    expect(commit_btn).to_be_visible()
    expect(commit_btn).to_contain_text("Commit 1 change")
    expect(commit_btn).to_be_enabled()

    # Clicking the commit button sends the commit prompt to the agent.
    commit_btn.click()

    # The agent receives the commit prompt, making 4 messages total (prompt,
    # response, commit prompt, response).
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)


@user_story("to discard changes to a single file via the Changes panel")
def test_discard_file_removes_from_changes(sculptor_instance_: SculptorInstance) -> None:
    """Discarding a file removes it from the Changes panel.

    Write two files, open the Changes panel (Uncommitted scope reveals the
    discard control), hover over one file to reveal the discard button, click it,
    confirm the dialog, and verify only one file remains.
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _WRITE_TWO_FILES_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(2)

    # Hover over discard_me.py to reveal the discard button.
    discard_row = tree_rows.filter(has_text="discard_me.py")
    expect(discard_row).to_have_count(1)
    discard_row.hover()

    discard_button = changes_panel.get_discard_button(discard_row)
    expect(discard_button).to_be_visible()
    discard_button.click()

    # The confirmation dialog appears.
    dialog = changes_panel.get_discard_dialog()
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("discard_me.py")
    expect(dialog).to_contain_text("cannot be undone")

    changes_panel.get_discard_dialog_confirm().click()

    # Dialog closes and the file is removed from the list.
    expect(dialog).to_be_hidden()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("keep.py")


@user_story("to cancel the discard dialog without losing changes")
def test_discard_cancel_preserves_file(sculptor_instance_: SculptorInstance) -> None:
    """Cancelling the discard dialog leaves the file in the Changes panel."""
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _WRITE_TWO_FILES_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(2)

    # Hover and click discard on discard_me.py.
    discard_row = tree_rows.filter(has_text="discard_me.py")
    discard_row.hover()
    changes_panel.get_discard_button(discard_row).click()

    dialog = changes_panel.get_discard_dialog()
    expect(dialog).to_be_visible()
    changes_panel.get_discard_dialog_cancel().click()

    # Dialog closes and both files are still listed.
    expect(dialog).to_be_hidden()
    expect(tree_rows).to_have_count(2)


@user_story("to see committed changes in the All scope after discarding the last uncommitted file")
def test_discard_last_uncommitted_keeps_all_scope_populated(sculptor_instance_: SculptorInstance) -> None:
    """Discarding the last uncommitted file must not clear the All scope.

    After discarding scratch.py (the only uncommitted change), the All scope
    should still show committed.py — it must NOT show "No changes".
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _COMMITTED_PLUS_UNCOMMITTED_PROMPT)

    # Uncommitted scope: only scratch.py is present.
    _select_uncommitted_scope(changes_panel)
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    uncommitted_rows = changes_tree.get_tree_rows()
    expect(uncommitted_rows).to_have_count(1)
    expect(uncommitted_rows.first).to_contain_text("scratch.py")

    # Hover over scratch.py to reveal the discard button, then discard it.
    uncommitted_rows.first.hover()
    discard_button = changes_panel.get_discard_button(uncommitted_rows.first)
    expect(discard_button).to_be_visible()
    discard_button.click()

    dialog = changes_panel.get_discard_dialog()
    expect(dialog).to_be_visible()
    changes_panel.get_discard_dialog_confirm().click()
    expect(dialog).to_be_hidden()

    # After discarding the last uncommitted file, the Uncommitted scope is empty.
    expect(uncommitted_rows).to_have_count(0)

    # Switch to the All scope — committed.py must still appear.
    _select_all_scope(changes_panel)

    all_tab_tree = changes_panel.get_changes_tree()
    expect(all_tab_tree).to_be_visible()
    all_tab_rows = all_tab_tree.get_tree_rows()
    expect(all_tab_rows).not_to_have_count(0)
    expect(all_tab_rows.filter(has_text="committed.py")).to_have_count(1)


@user_story("to see that the All scope button is enabled when a target branch is auto-resolved")
def test_all_scope_enabled_with_auto_resolved_target_branch(sculptor_instance_: SculptorInstance) -> None:
    """The test repo has a 'main' branch, so clone workspaces resolve
    target_branch to 'origin/main'; the All scope button should be enabled."""
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _WRITE_FILE_PROMPT)

    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_be_visible()
    expect(scope_all).to_be_enabled()


@user_story("to see diff content update when switching to All scope")
def test_switching_to_all_scope_shows_target_branch_diff(sculptor_instance_: SculptorInstance) -> None:
    """Switching to All scope shows the target-branch diff content (the
    uncommitted file as a new addition relative to the target branch)."""
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _WRITE_FILE_PROMPT)

    _select_all_scope(changes_panel)

    # The changes tree shows files (hello.py is new relative to the target branch).
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.filter(has_text="hello.py")).to_be_visible()


@user_story("to see the HEAD-vs-working-tree diff when opening a file in Uncommitted scope")
def test_scope_diff_mode_uncommitted_head_vs_working_tree(sculptor_instance_: SculptorInstance) -> None:
    """Opening a file in the Uncommitted scope shows the HEAD-to-working-tree diff
    (hello -> goodbye) as a modification."""
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _COMMIT_THEN_EDIT_PROMPT)

    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows).to_have_count(1)
    expect(tree_rows.first).to_contain_text("myapp.py")

    viewer = changes_panel.open_file("myapp.py")
    ensure_unified_view(viewer)

    diff_view = viewer.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    # Uncommitted diff: "hello" removed, "goodbye" added.
    expect(diff_view).to_contain_text("hello")
    expect(diff_view).to_contain_text("goodbye")

    # The header shows a modification (+1/-1), not a full addition.
    diff_header = viewer.get_file_header()
    expect(diff_header).to_contain_text("myapp.py")
    expect(diff_header).to_contain_text("+1")
    expect(diff_header).to_contain_text("-1")


@user_story("to see the merge-base-vs-working-tree diff when opening a file in All scope")
def test_scope_diff_mode_all_merge_base_vs_working_tree(sculptor_instance_: SculptorInstance) -> None:
    """Opening a file in the All scope shows the merge-base-to-working-tree diff
    (the whole file as the current "goodbye" content, with no "hello")."""
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _COMMIT_THEN_EDIT_PROMPT)

    _select_all_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    app_row = changes_tree.get_tree_rows().filter(has_text="myapp.py")
    expect(app_row).to_be_visible()

    viewer = changes_panel.open_file("myapp.py")
    ensure_unified_view(viewer)

    diff_view = viewer.get_unified_diff_views()
    expect(diff_view).to_be_visible()
    # All diff (merge-base -> working tree): current content "goodbye" as an
    # addition. "hello" must NOT appear since the working tree was already edited.
    expect(diff_view).to_contain_text("goodbye")
    expect(diff_view).not_to_contain_text("hello")


@user_story("to see moved files rendered cleanly with R status and no redundant rename label")
def test_moved_file_shows_r_status_without_rename_label(sculptor_instance_: SculptorInstance) -> None:
    """Moved files show an R status without a redundant old→new name label.

    When a file is moved to a new folder without changing its name, the Changes
    panel (All scope) shows only the file in its new location with an R (renamed)
    status indicator — no "oldName →" label that duplicates the filename.
    ``src/helpers.py`` exists on the target branch (main), so committing the move
    yields a rename in the vs-target-branch diff.
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _RENAME_FILE_PROMPT)

    _select_all_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()

    file_row = changes_tree.get_tree_rows().filter(has_text="helpers.py")
    expect(file_row).to_be_visible()

    status = changes_tree.get_row_status(file_row)
    expect(status).to_have_text("R")

    # The row must NOT contain the "→" rename arrow — the old-name label is
    # not rendered when the filename itself didn't change.
    expect(file_row).not_to_contain_text("→")


@user_story("to see a clean Changes panel when a directory has been replaced by a symlink")
def test_directory_replaced_by_symlink_no_duplicate_row(sculptor_instance_: SculptorInstance) -> None:
    """When a directory is replaced by a symlink at the same path, the Changes
    tree must not render two distinct rows for that path.

    ``addDeletedFileToTree`` synthesizes a folder node to host the diff's deleted
    children; when the file list already contains a *file* node at the same path
    (the symlink), a buggy synthesis creates a sibling node with the same path and
    the virtualizer renders two overlapping "mydir" rows.
    """
    page = sculptor_instance_.page
    _, changes_panel = _open_changes_panel_with(page, _SYMLINK_REPRO_PROMPT)

    # The repro needs the uncommitted scope: the directory commit is HEAD, the
    # symlink is the working tree, so the uncommitted diff carries the D entries
    # for foo.md/bar.md while the file list carries ``mydir`` as a (symlink) file.
    _select_uncommitted_scope(changes_panel)

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()

    # Wait for the deleted children to render before counting — they are
    # injected by ``addDeletedFileToTree`` once the diff is parsed, which is
    # exactly the synthesis that can create the duplicate node.
    expect(tree_rows.filter(has_text="foo.md")).to_have_count(1)
    expect(tree_rows.filter(has_text="bar.md")).to_have_count(1)

    # Count rows whose display name (first line of innerText) is exactly
    # ``mydir`` — e.g. ``mydir\n+1\nA`` (the symlink file) or ``mydir\n2`` (the
    # synthesized folder with badge count 2). The buggy state has two such rows;
    # the fixed state has exactly one. The two rows share the path and carry no
    # distinguishing testid, so the names are read via a locator ``evaluate_all``
    # (a budgeted exception to the no-integration-page-evaluate rule). The
    # inputs that gate the duplicate (file list + diff) have settled via the
    # assertions above, so a one-shot count is reliable.
    name_counts = tree_rows.evaluate_all(
        "els => { const c = {}; for (const e of els) { const n = e.innerText.split('\\n')[0]; c[n] = (c[n] || 0) + 1; } return c; }"
    )
    mydir_row_count = name_counts.get("mydir", 0)
    failure_message = (
        f"Expected exactly one row named 'mydir' in the changes tree, got {mydir_row_count}."
        + f" Row name counts were {name_counts}. Two 'mydir' rows means useFileTree synthesised"
        + " a duplicate node when the symlink replaced the directory."
    )
    assert mydir_row_count == 1, failure_message
