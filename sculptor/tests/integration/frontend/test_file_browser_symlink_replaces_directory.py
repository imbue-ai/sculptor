"""Reproduce the duplicate-row rendering bug in the Changes tab when a tracked
directory is deleted and replaced with a symlink at the same path.

Reported scenario: a tracked directory (e.g. ``.claude/skills/create-html-mock/``)
was deleted and replaced with a symlink at the same path. The Changes tab in
the File Browser then renders two rows on top of each other, and in dev React
logs:

    Warning: Encountered two children with the same key, ``...``

The duplicate originates in ``useFileTree`` (sculptor/frontend/src/pages/workspace/
panels/fileBrowser/hooks.ts): ``addDeletedFileToTree`` walks the tree to inject
nodes for files reported as deleted in the diff but absent from the file list,
and only matches existing folders by ``n.type === "directory"``. A file at the
same path (the symlink) doesn't match, so a sibling directory is created at the
same path → two TreeNodes share ``node.path`` → the virtualizer's
``key={node.path}`` collides.

Note: this test runs against a production React build, where the duplicate-key
warning is suppressed. We assert on the rendered DOM directly: at most one row
should display ``mydir`` as its name in the changes tree. The buggy state
shows two: one for the symlink file and one for the synthesized parent folder
of the deleted children.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Step 1: create and commit a directory containing two files. They become the
#         deleted entries in the diff after step 2.
# Step 2: delete the directory, replace it with a symlink at the same path
#         (``mydir`` now points at the existing ``stuff.txt``), and stage the
#         result so the symlink is tracked. ``git ls-files`` will then return
#         ``mydir`` as a regular file and ``git diff HEAD`` will show
#         ``D mydir/foo.md`` and ``D mydir/bar.md`` alongside ``A mydir``.
#         This is the exact data shape that confuses ``addDeletedFileToTree``:
#         the file list has ``mydir`` as a file at the same path that the
#         deleted-files synthesizer wants to materialize as a directory.
_REPRO_PROMPT = """\
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


@user_story("to see a clean Changes tab when a directory has been replaced by a symlink")
def test_directory_replaced_by_symlink_no_duplicate_row(sculptor_instance_: SculptorInstance) -> None:
    """When a directory is replaced by a symlink at the same path, the Changes
    tab must not render two distinct rows for the same path.

    Without the fix, ``addDeletedFileToTree`` synthesizes a folder named
    ``mydir`` to host the deleted children even though the file list already
    contains a *file* node at ``mydir`` (the symlink). The tree then has two
    sibling TreeNodes with the same path, the virtualizer renders both with
    ``key={node.path}``, and the user sees overlapping rows.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_REPRO_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # The bug lives in the Changes tab tree. Use the uncommitted scope: the
    # commit in step 1 is HEAD, the symlink in step 2 is the working tree, so
    # the uncommitted diff carries D entries for foo.md and bar.md while the
    # file list carries ``mydir`` as a (symlink) file.
    task_page.activate_changes_panel(scope="uncommitted")

    file_browser = task_page.get_file_browser()
    changes_tree = file_browser.get_changes_tree()
    expect(changes_tree).to_be_visible()

    # Refresh once to force the file list and diff to be re-fetched together,
    # closing the stale-data race in ``useWorkspaceFileList`` that can briefly
    # hide the bug. After the refresh, both views observe the post-symlink
    # state and the duplicate node is generated.
    refresh_btn = file_browser.get_refresh_button()
    refresh_btn.click()

    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.first).to_be_visible()

    # All four expected rows must appear: the symlink ``mydir`` plus the two
    # deleted children. Wait for the deleted children to render before
    # counting — they're injected by ``addDeletedFileToTree`` which depends on
    # the diff being parsed. ``foo.md`` and ``bar.md`` only appear if that
    # synthesis ran, which is also exactly what triggers the bug.
    expect(tree_rows.filter(has_text="foo.md")).to_have_count(1)
    expect(tree_rows.filter(has_text="bar.md")).to_have_count(1)

    # Count rows whose display name (first line of innerText) is exactly
    # ``mydir`` — for example ``mydir\n+1\nA`` (the symlink file) or
    # ``mydir\n2`` (the synthesized folder with badge count 2). The buggy
    # state has two such rows; the fixed state should have exactly one. All
    # the inputs that gate the duplicate (file list, diff, refresh) have
    # already settled by the assertions above, so a one-shot count is
    # reliable.
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
