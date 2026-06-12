"""Regression test: Individual file diff must fetch oldLines from HEAD in
uncommitted scope.

When viewing uncommitted changes (HEAD → working tree), the "old" file
content for hunk expansion must come from HEAD — not from the target branch.
The Changes tab defaults to "All" (vs-target-branch) scope, which correctly
uses the target branch ref.  This test explicitly switches to "Uncommitted"
scope to verify that HEAD is used there.

Without baseRefOverride="HEAD" in the uncommitted scope, useFileLines falls
back to getBaseRef() which returns e.g. "main".  When committed changes on
the workspace branch significantly alter a file's line count vs "main",
Pierre's DiffHunksRenderer crashes with "newLine or oldLine doesnt exist
for context" because the target-branch line array is too short.

This is the same class of bug as the Review All / Shiki regression
(test_regression_review_all_shiki_error.py), but affects the individual file
diff panel rather than the combined review view.
"""

import json

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
        "command": "git add README.md && git commit -m 'Expand README to 600 lines'"
      }}
    }},
    {_EDIT_STEPS}
  ]
}}`"""


@user_story("to view an individual file diff without the diff panel crashing")
def test_individual_file_diff_does_not_crash_with_committed_line_count_changes(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Opening an individual file diff must request old file content from HEAD.

    The diff panel shows uncommittedDiff (HEAD → working tree), so
    useFileLines must pass gitRef="HEAD" to the read-file-at-ref API.
    Without the baseRefOverride="HEAD" fix, it falls back to the target
    branch (e.g. "main") whose file may have a completely different line
    count, causing Pierre to crash.
    """
    page = sculptor_instance_.page

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

    task_page = start_task_and_wait_for_ready(page, prompt=_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Switch to the Changes tab and explicitly select the "Uncommitted" scope.
    # The default scope is "All" (vs-target-branch), which correctly uses the
    # target branch ref.  This test verifies the uncommitted scope uses HEAD.
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
    # use gitRef="HEAD", not the target branch.  Without baseRefOverride,
    # useFileLines falls back to getBaseRef() which returns "main" for this
    # test repo (no targetBranch configured).  "main" has ~2 lines while
    # HEAD has 600, causing Pierre to crash on hunk offset lookups.
    readme_refs = [ref for ref in captured_git_refs if ref]
    assert len(readme_refs) > 0, "Expected at least one read-file-at-ref call for README.md"
    assert all(ref == "HEAD" for ref in readme_refs), (
        f"read-file-at-ref for README.md used wrong git ref: {readme_refs}. "
        + "Expected 'HEAD' but got a target-branch ref, which would cause Pierre to crash "
        + "when committed changes alter the file's line count vs the target branch."
    )
