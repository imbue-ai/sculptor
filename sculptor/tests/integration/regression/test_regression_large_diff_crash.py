"""Regression test: Individual file diff must fetch oldLines from the head
commit in uncommitted scope.

When viewing uncommitted changes (HEAD → working tree), the "old" file
content for hunk expansion must come from the workspace's head commit, which
the backend names on the diff artifact as the uncommitted diff's base — not
from the target branch. The Changes tab defaults to "All" (vs-target-branch)
scope, which uses the target's merge base. This test explicitly switches to
"Uncommitted" scope to verify that the head commit is used there.

When committed changes on the workspace branch significantly alter a file's
line count vs the target, reading oldLines at the target makes Pierre's
DiffHunksRenderer crash with "newLine or oldLine doesnt exist for context"
because the target-branch line array is too short.

This is the same class of bug as the Review All / Shiki regression
(test_regression_review_all_shiki_error.py), but affects the individual file
diff panel rather than the combined review view.
"""

import json
from pathlib import Path

from playwright.sync_api import Response
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Strategy: README.md exists on the "main" branch with only ~2 lines.
# We overwrite it with 600 lines and commit on the workspace branch, then
# make multi-hunk uncommitted edits at widely-spaced positions.
#
# The uncommittedDiff (HEAD → working dir) has hunks referencing old lines up
# to ~590, but useFileLines fetches oldLines from "main" (~2 lines).  Pierre
# tries to look up context at old line 100+ but oldLines only has 2 entries.
_LONG_README = "\\n".join(f"# Section {i}" for i in range(600))

# Build edit steps that modify lines at spread positions to create multiple
# hunks, ensuring the diff spans widely-spaced line numbers.
_EDIT_STEPS = ",".join(
    f"""
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "README.md",
        "old_string": "# Section {i}",
        "new_string": "# Section {i} MODIFIED"
      }}
    }}"""
    for i in (5, 100, 200, 300, 400, 500, 590)
)


def _prompt(head_commit_file: Path) -> str:
    """Commit a 600-line README, record the new head commit in `head_commit_file`, then edit the README."""
    return f"""\
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
        "command": "git add README.md && git commit -m 'Expand README to 600 lines'"
      }}
    }},
    {{
      "command": "bash",
      "args": {{
        "command": "git rev-parse HEAD > '{head_commit_file}'"
      }}
    }},
    {_EDIT_STEPS}
  ]
}}`"""


@user_story("to view an individual file diff without the diff panel crashing")
def test_individual_file_diff_does_not_crash_with_committed_line_count_changes(
    sculptor_instance_: SculptorInstance, tmp_path: Path
) -> None:
    """Opening an individual file diff must request old file content at the head commit.

    The diff panel shows uncommittedDiff (HEAD → working tree), so useFileLines
    must read the old side at the workspace's head commit. Reading it at the
    target branch, whose README has a completely different line count, makes
    Pierre crash.
    """
    page = sculptor_instance_.page
    head_commit_file = tmp_path / "head_commit"

    # Capture the gitRef used in read-file-at-ref requests for README.md.
    captured_git_refs: list[str] = []

    def _on_response(response: Response) -> None:
        if "read-file-at-ref" not in response.url:
            return
        try:
            req_body = response.request.post_data
            if req_body and "README" in req_body:
                parsed = json.loads(req_body)
                captured_git_refs.append(parsed.get("gitRef", ""))
        except (json.JSONDecodeError, AttributeError):
            pass

    page.on("response", _on_response)

    task_page = start_task_and_wait_for_ready(page, prompt=_prompt(head_commit_file))
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    head_commit_id = head_commit_file.read_text().strip()

    # Switch to the Changes tab and explicitly select the "Uncommitted" scope.
    # The default scope is "All" (vs-target-branch), which uses the target's
    # merge base.  This test verifies the uncommitted scope uses the head commit.
    task_page.activate_changes_panel(scope="uncommitted")

    changes_panel = task_page.get_changes_panel()
    changes_tree = changes_panel.get_changes_tree()
    file_row = changes_tree.get_tree_rows().filter(has_text="README")
    expect(file_row.first).to_be_visible()
    file_row.first.click()

    # Wait for the diff to render and useFileLines to fetch old content.
    # Use DIFF_PANEL (not DIFF_VIEW_UNIFIED) because the view type may be
    # "split" if a prior test in the shared instance toggled the setting.
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    expect(diff_panel).to_contain_text("MODIFIED")

    # The key assertion: the read-file-at-ref request for README.md must
    # use the head commit, not the target branch.  The target's README has
    # ~2 lines while the head commit's has 600, so a target read crashes
    # Pierre on hunk offset lookups.
    readme_refs = [ref for ref in captured_git_refs if ref]
    assert len(readme_refs) > 0, "Expected at least one read-file-at-ref call for README.md"
    assert all(ref == head_commit_id for ref in readme_refs), (
        f"read-file-at-ref for README.md used wrong git ref: {readme_refs}. "
        + f"Expected the head commit {head_commit_id}; any other ref, such as the target branch, "
        + "makes Pierre crash when committed changes alter the file's line count vs the target branch."
    )
