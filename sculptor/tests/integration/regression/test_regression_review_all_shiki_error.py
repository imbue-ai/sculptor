"""Regression test: Review All diff must remain visible after syntax
highlighting kicks in, even when committed changes increase a file's line count
relative to the target branch.

The bug: CombinedDiffView uses `uncommittedDiff` (HEAD → working directory),
but `useFileLines` fetches `oldLines` from the target branch.  When committed
changes add many lines to a file, the target-branch version is shorter than
HEAD.  Shiki then tries to apply decoration positions from the (long) HEAD-based
diff onto the (short) target-branch `oldLines`, crashing the diff view.
The diff initially appears but disappears once decorations are applied.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Build a 200-line file.  JSON newlines are represented as \\n.
_LONG_README = "\\n".join(f"# Line {i}" for i in range(200))

# Strategy: Use README.md which already exists on `main` (the target branch)
# with only ~2 lines.  Overwrite it with 200 lines and commit on the workspace
# branch, then make multiple uncommitted edits at widely-spaced positions to
# create a multi-hunk diff.
#
# When Review All opens, `useFileLines` fetches `oldLines` from `main`
# (~2 lines), but the `uncommittedDiff` (HEAD → working dir) has hunks
# referencing line positions up to ~195.  This mismatch causes Shiki to
# render "Invalid decoration position" as visible error text in the UI.
_PROMPT = f"""\
fake_claude:multi_step `{{
  "steps": [
    {{
      "command": "write_file",
      "args": {{
        "file_path": "README.md",
        "content": "{_LONG_README}\\n"
      }}
    }},
    {{
      "command": "bash",
      "args": {{
        "command": "git add README.md && git commit -m 'Expand README to 200 lines'"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "README.md",
        "old_string": "# Line 5",
        "new_string": "# Line 5 MODIFIED"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "README.md",
        "old_string": "# Line 100",
        "new_string": "# Line 100 MODIFIED"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "README.md",
        "old_string": "# Line 195",
        "new_string": "# Line 195 MODIFIED"
      }}
    }}
  ]
}}`"""


@user_story("to review all changes without the diff crashing when branch has committed line-count changes")
def test_review_all_diff_stays_visible_with_committed_line_count_changes(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Review All diff must remain visible after syntax highlighting kicks in.

    When a file grows significantly via committed changes (relative to the base
    branch), opening Review All should render the diff and keep it visible.
    The bug caused the diff to initially appear but then crash once Shiki
    decorations were applied, because oldLines came from the wrong ref.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Switch to the Changes tab and open Review All
    task_page.activate_changes_panel()
    task_page.click_review_all()

    review_all_panel = task_page.get_review_all_panel()
    expect(review_all_panel).to_be_visible()

    # The combined diff should show the file header and diff content.
    expect(review_all_panel).to_contain_text("README.md")
    expect(review_all_panel).to_contain_text("MODIFIED")

    # Wait for syntax highlighting decorations to be applied — the bug caused
    # the diff to disappear at this point because decorations referenced
    # invalid line positions.
    page.wait_for_timeout(3000)

    # The diff must still be visible and contain the changed content after
    # decorations have been processed.
    expect(review_all_panel).to_contain_text("README.md")
    expect(review_all_panel).to_contain_text("MODIFIED")
