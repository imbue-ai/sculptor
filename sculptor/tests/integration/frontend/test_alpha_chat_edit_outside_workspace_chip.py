"""Integration test: Edit tool calls to files OUTSIDE the workspace must still render.

Regression test for a bug where ``Edit`` / ``MultiEdit`` tool calls targeting a
file outside the agent's code directory (e.g. the global Claude memory dir under
``~/.claude/.../memory/``) silently vanished from the alpha chat UI, even though
they appeared in the transcript.

Root cause: the diff tracker returns ``None`` for files outside the code
directory, and the backend's synthetic-diff fallback only covered ``Write`` --
so out-of-workspace ``Edit`` calls fell back to ``GenericToolContent`` (which
carries no ``file_path``). The frontend routes diff tools into the file-chip
path, then drops any chip whose path it cannot derive -- so the edit disappeared.

A ``Write`` to the same location renders fine (it has a synthetic-diff fallback),
which is what made the behaviour look inconsistent.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# An absolute path outside the agent's workspace/code directory, mirroring how
# the global Claude memory dir lives outside the repo. A leading-slash path makes
# fake_claude's ``Path(cwd) / file_path`` resolve to exactly this location.
_OUTSIDE_DIR = "/tmp/sculptor_outside_ws_edit_test"
_OUTSIDE_FILE = f"{_OUTSIDE_DIR}/memory_notes.md"

# bash creates the out-of-workspace file (rendered as a bash block, not a chip),
# then edit_file edits it. The edit is the tool call that used to disappear.
EDIT_OUTSIDE_WORKSPACE_PROMPT = f"""\
fake_claude:multi_step `{{
  "steps": [
    {{
      "command": "bash",
      "args": {{
        "command": "mkdir -p {_OUTSIDE_DIR} && printf 'original line\\\\n' > {_OUTSIDE_FILE}"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "{_OUTSIDE_FILE}",
        "old_string": "original line",
        "new_string": "updated line"
      }}
    }}
  ]
}}`"""


@user_story("to see Edit tool calls to files outside the workspace rendered as chips")
def test_edit_outside_workspace_renders_file_chip(sculptor_instance_: SculptorInstance) -> None:
    """An Edit to a file outside the code directory still shows a file chip."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=EDIT_OUTSIDE_WORKSPACE_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # The out-of-workspace Edit must render as a file chip naming the edited file.
    # Before the fix this chip was silently dropped (count 0).
    file_chips = alpha_view.get_file_chips()
    expect(file_chips).to_have_count(1)
    expect(file_chips.first).to_be_visible()
    expect(file_chips.first).to_contain_text("memory_notes.md")
