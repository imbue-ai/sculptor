"""Regression test: Review All combined diff must remain visible after
syntax highlighting kicks in when the scope picker is on "All", even when
committed changes have *shrunk* a file relative to the target branch.

This is the inverse of `test_regression_review_all_shiki_error.py`, which
exercises the same diff surface in the `uncommitted` scope after committed
changes have *grown* a file.  The two failure modes share a root cause
(`useFileLines` fetching oldLines from the wrong git ref for the active
scope) but trigger from opposite directions.

The bug (SCU-1269): CombinedDiffView's `ExpandableFileDiff` hardcoded the
base ref passed to `useFileLines` to "HEAD".  When the scope picker is on
"All" the active diff is `<target>..workdir`, so the diff's old-side line
numbers come from the target branch (e.g. up to line 75 for
`src/helpers.py` on main).  With oldLines fetched from HEAD instead —
which can be far shorter after a committed shrink — Pierre's
context-expansion and Shiki decorations operate on out-of-range positions
and the diff disappears.  The fix mirrors the per-scope handling already
used in the single-file DiffPanel view: when scope is `vs-target-branch`,
let `useFileLines` fall back to the target branch ref.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_viewer import wait_for_full_content_diff_render
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Strategy: src/helpers.py is 75 lines on `main` (the target branch).  This
# prompt overwrites it with a 25-line version on the workspace branch and
# commits, producing a two-hunk diff against main where the second hunk
# starts at old-side line 49 and the file continues to line 75.  After the
# commit:
#   * main (target): 75 lines
#   * HEAD:          25 lines
# Pierre's context-expansion loop accesses oldLines[32]..oldLines[47]
# (between the two hunks).  When oldLines is mistakenly fetched from HEAD
# (25 entries) rather than from main (75 entries), those accesses fall off
# the end of the array and either Pierre's renderHunks throws or Shiki
# applies a decoration at an out-of-range line — in both cases the diff
# is replaced by an error message.
_PROMPT = """\
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
        "command": "git add -A && git commit -m 'Shrink helpers.py'"
      }
    }
  ]
}`"""


@user_story(
    "to review all changes in the All scope without the combined diff crashing when target branch is longer than HEAD"
)
def test_review_all_diff_stays_visible_when_target_branch_longer_than_head(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Combined "All" scope diff must remain visible when target > HEAD.

    Inverse of `test_review_all_diff_stays_visible_with_committed_line_count_changes`:
    that test exercises the combined `uncommitted` scope when HEAD grows
    past the target branch.  This test exercises the combined
    `vs-target-branch` (All) scope when HEAD has shrunk below the target
    branch length.
    """
    page = sculptor_instance_.page

    # Capture Pierre's hunk-renderer crash. Pierre throws during hunk expansion
    # from its async Shiki highlight callback (outside React's render cycle, so
    # the FileDiff error boundary does not catch it), surfacing as an uncaught
    # pageerror or a console error rather than replacing the body with a banner.
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(err.message))
    page.on("console", lambda msg: js_errors.append(msg.text) if msg.type == "error" else None)

    task_page = start_task_and_wait_for_ready(page, prompt=_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes tab and the Review All combined diff.
    task_page.activate_changes_panel()
    task_page.click_review_all()

    review_all_panel = task_page.get_review_all_panel()
    expect(review_all_panel).to_be_visible()

    # Switch the scope picker to "All" — the bug only manifests for the
    # vs-target-branch combined diff path.
    all_scope = review_all_panel.get_scope_all()
    expect(all_scope).to_be_visible()
    all_scope.click()

    # Combined diff should show the shrunk helpers.py header and content.
    expect(review_all_panel).to_contain_text("helpers.py")
    expect(review_all_panel).to_contain_text("is_even")

    # Block until Pierre's full-content render pass — the pass that reads the
    # fetched old/new line arrays at the diff's merge-base-aligned hunk indices,
    # and where the wrong-ref bug either crashes the renderer or applies an
    # out-of-range Shiki decoration — has run all the way through the LAST hunk.
    # The two-hunk deletion diff drops the trailing truncate() group, so its last
    # hunk's final deleted line is truncate's body; is_even is unchanged context
    # in the collapsed gap between the hunks and paints in the first partial pass,
    # so it cannot gate this second pass. helpers.py is Modified, so the combined
    # view honors the shared unified/split preference; the anchor pierces either
    # view's <diffs-container> shadow root, so no view needs forcing here.
    wait_for_full_content_diff_render(page, "return text[:max_length - 3]")

    # Diff must still be visible afterwards.
    expect(review_all_panel).to_contain_text("helpers.py")
    expect(review_all_panel).to_contain_text("is_even")
    # No Shiki crash banner.
    expect(review_all_panel).not_to_contain_text("Invalid decoration position")

    # Defense in depth: Pierre must not have crashed during hunk expansion. The
    # crash message names Pierre's renderer: "renderHunks" in older @pierre/diffs
    # releases, "DiffHunksRenderer" in 1.2.x.
    render_hunks_errors = [e for e in js_errors if "renderHunks" in e or "DiffHunksRenderer" in e]
    assert not render_hunks_errors, f"Pierre renderHunks crash: {render_hunks_errors[:1]}"
