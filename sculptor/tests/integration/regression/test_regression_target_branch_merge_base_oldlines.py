"""Regression test (SCU-1371): vs-target-branch diff must fetch oldLines from
the merge-base commit, not the target-branch tip.

The "All" scope renders ``targetBranchDiff``, which the backend computes as a
three-dot diff against ``merge-base(target, HEAD)`` — so the hunks' old-side
line numbers reference the *merge-base* content.  ``useFileLines``, however,
fetched ``oldLines`` from the target-branch *tip* (e.g. ``main``).

Those two refs only agree when the target branch has not modified the file
since the branch point.  When ``main`` shortens the file after the branch
point, the tip content is shorter than the old-side line numbers the merge-base
diff references, so Pierre's context-expansion indexes past the end of the
(shorter) ``oldLines`` array and renderHunks throws::

    renderHunks: oldLine and newLine are null, something is wrong

This is the same crash class as ``test_regression_review_all_shiki_error*`` and
``test_regression_large_diff_crash`` — but those exercised the scope→ref
selection (HEAD vs target branch).  They still fetched the target-branch *tip*,
so this merge-base-vs-tip case stayed latent until the target branch itself
diverged.

Strategy
--------
``src/helpers.py`` is 75 lines on ``main`` (the merge-base at branch time).
The default worktree workspace branches off ``main``, so ``main`` is its target
branch.  The agent:

1. Shrinks ``src/helpers.py`` to 25 lines and commits it on the workspace
   branch.  The vs-target-branch diff (merge-base → working tree) is then a
   two-hunk diff whose context gap references old-side lines well past line 25.
2. Advances ``main`` to a divergent commit (parented on the original
   merge-base) whose ``src/helpers.py`` is a single line.  Crucially this keeps
   ``merge-base(HEAD, main)`` at the original 75-line commit, so the diff is
   unchanged — only the *tip* content shrinks.

With the bug, ``useFileLines`` fetches ``oldLines`` from the 1-line tip and
Pierre crashes.  The fix fetches ``oldLines`` from the 75-line merge-base
commit, so the read-file-at-ref request uses the merge-base SHA (a 40-char
hex commit id) instead of the ``main`` branch name.
"""

import json
import re

from playwright.sync_api import Response
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_viewer import wait_for_full_content_diff_render
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# 25-line src/helpers.py: keeps the middle function group and drops the first
# and last groups from the 75-line `main` version.  This yields a two-hunk
# vs-target-branch diff whose gap between the hunks makes Pierre's expansion
# loop read old-side indices in the 30s/40s — valid in the 75-line merge-base,
# but out of range for the shrunk `main` tip.
_SHRUNK_HELPERS = (
    "# Helper utilities for the project.\\n\\n\\n"
    + "def is_even(n):\\n    return n % 2 == 0\\n\\n\\n"
    + "def is_odd(n):\\n    return n % 2 != 0\\n\\n\\n"
    + "def clamp(value, min_val, max_val):\\n    return max(min_val, min(max_val, value))\\n\\n\\n"
    + "def reverse_string(s):\\n    return s[::-1]\\n\\n\\n"
    + "def count_vowels(s):\\n    return sum(1 for c in s.lower() if c in 'aeiou')\\n\\n\\n"
    + "def flatten(nested):\\n    return [item for sublist in nested for item in sublist]\\n"
)

# Advance the target branch (main) to a commit that shortens src/helpers.py to a
# single line, parented on the *current* main (the merge-base) so
# merge-base(HEAD, main) is unchanged.  Uses a throwaway index (GIT_INDEX_FILE)
# and plumbing so the workspace working tree, index, and HEAD are left untouched
# — only the branch ref moves.  update-ref works even though main is checked out
# in the repo's primary worktree.
_ADVANCE_MAIN = (
    "B=$(echo x | git hash-object -w --stdin); "
    + "export GIT_INDEX_FILE=$(mktemp); "
    + "git read-tree main; "
    + "git update-index --add --cacheinfo 100644,$B,src/helpers.py; "
    + "T=$(git write-tree); "
    + "C=$(GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t.com "
    + "git commit-tree $T -p main -m short); "
    + "rm -f $GIT_INDEX_FILE; unset GIT_INDEX_FILE; "
    + "git update-ref refs/heads/main $C"
)

_PROMPT = f"""\
fake_claude:multi_step `{{
  "steps": [
    {{
      "command": "write_file",
      "args": {{
        "file_path": "src/helpers.py",
        "content": "{_SHRUNK_HELPERS}"
      }}
    }},
    {{
      "command": "bash",
      "args": {{
        "command": "git add -A && git commit -m 'Shrink helpers.py on branch'"
      }}
    }},
    {{
      "command": "bash",
      "args": {{
        "command": "{_ADVANCE_MAIN}"
      }}
    }}
  ]
}}`"""

_SHA_RE = re.compile(r"[0-9a-f]{40}")


@user_story("to open a vs-target-branch file diff without it crashing when the target branch diverged")
def test_target_branch_diff_fetches_oldlines_from_merge_base(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The vs-target-branch (All scope) diff must request old file content at
    the merge-base commit, not the target-branch tip.

    The diff is computed against merge-base(main, HEAD), so the old-side line
    numbers reference the merge-base.  Fetching oldLines from the target-branch
    tip (main) — which shortened after the branch point — gives a too-short
    array and crashes Pierre's renderHunks.
    """
    page = sculptor_instance_.page

    # Capture the gitRef used for src/helpers.py read-file-at-ref requests (the
    # "old" side of the diff).
    captured_helpers_refs: list[str] = []

    def _on_response(response: Response) -> None:
        if "read-file-at-ref" not in response.url:
            return
        try:
            req_body = response.request.post_data
            if req_body and "helpers.py" in req_body:
                parsed = json.loads(req_body)
                captured_helpers_refs.append(parsed.get("gitRef", ""))
        except (json.JSONDecodeError, AttributeError):
            pass

    page.on("response", _on_response)

    # Also capture renderHunks crashes — Pierre throws during hunk expansion
    # from its async Shiki highlight callback (outside React's render cycle, so
    # the FileDiff error boundary does not catch it), surfacing as an uncaught
    # pageerror that leaves the diff body empty.
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(err.message))
    page.on("console", lambda msg: js_errors.append(msg.text) if msg.type == "error" else None)

    task_page = start_task_and_wait_for_ready(page, prompt=_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes tab in the default "All" (vs-target-branch) scope and
    # open the single-file diff for helpers.py.
    task_page.activate_changes_panel()

    changes_panel = task_page.get_changes_panel()
    changes_tree = changes_panel.get_changes_tree()
    file_row = changes_tree.get_tree_rows().filter(has_text="helpers.py")
    expect(file_row.first).to_be_visible()
    file_row.first.click()

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    # Wait (bounded, breaks as soon as the condition holds — not a fixed sleep)
    # for useFileLines to issue the old-side ("vs target branch") content fetch
    # for helpers.py.  This fetch precedes Pierre's hunk expansion, so it is
    # observed even when the buggy ref later makes Pierre crash and the diff
    # body fails to render.  This is the deterministic signal that distinguishes
    # the bug (ref "main") from the fix (the merge-base SHA), so it gates the
    # test and fails fast under the bug instead of timing out on empty body text.
    for _ in range(60):
        if any(captured_helpers_refs):
            break
        page.wait_for_timeout(250)

    # The old-side content for helpers.py must be fetched at the merge-base
    # commit (a 40-char hex SHA), not the target-branch tip "main".
    helpers_refs = [ref for ref in captured_helpers_refs if ref]
    assert helpers_refs, "Expected at least one read-file-at-ref call for src/helpers.py old content"
    assert all(_SHA_RE.fullmatch(ref) for ref in helpers_refs), (
        f"read-file-at-ref for src/helpers.py used {helpers_refs}, but the "
        + "vs-target-branch diff is computed against merge-base(main, HEAD), "
        + "so oldLines must come from that merge-base commit SHA — not the "
        + "target-branch tip 'main', whose helpers.py is shorter than the "
        + "merge-base line numbers the diff references (the SCU-1371 crash)."
    )

    # Force unified so the deterministic render anchor has a single shadow-root
    # body to pierce (the split/unified preference persists across the shared
    # instance, so a prior test can leave it on either view).
    diff_panel.ensure_unified_mode()

    # Block until Pierre's full-content render pass — the pass whose merge-base
    # aligned hunk indices read the fetched old/new line arrays, and where the
    # crash fires — has run all the way through the LAST hunk. The two-hunk
    # deletion diff drops the trailing truncate() group, so its last hunk's
    # final deleted line is truncate's body; the 16-line unchanged gap between
    # the hunks stays a COLLAPSED (expandable) separator, so gap-only context
    # like is_even paints in the first partial pass and would let the read fire
    # too early. Anchoring on the expandable separator plus the last hunk's
    # deleted line guarantees the whole risky pass has run before errors are read.
    wait_for_full_content_diff_render(page, "return text[:max_length - 3]")

    # With the fix the expandable diff renders correctly, so the changed content
    # is visible.
    expect(diff_panel).to_contain_text("is_even")

    # Defense in depth: Pierre must not have crashed during hunk expansion. The
    # crash message names Pierre's renderer: "renderHunks" in older @pierre/diffs
    # releases, "DiffHunksRenderer" in 1.2.x.
    render_hunks_errors = [e for e in js_errors if "renderHunks" in e or "DiffHunksRenderer" in e]
    assert not render_hunks_errors, f"Pierre renderHunks crash: {render_hunks_errors[:1]}"
