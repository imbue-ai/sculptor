"""Regression test: turn footer must report Bash-created files in WORKTREE workspaces.

In WORKTREE mode the workspace's ``.git`` is a gitfile (a file containing a
``gitdir:`` pointer), not a directory.  ``DiffTracker._get_tree_hash_with_untracked_and_unstaged_changes``
used to hardcode ``.git/index`` and ``.git/objects``, which only exist in
non-worktree repos.  In a WORKTREE workspace the slow path therefore raised,
``TurnMetrics.changed_files`` came back empty, and the turn footer's file
chip never showed up for changes that came from a Bash tool.

Files created by ``write_file`` (Edit/Write/MultiEdit) are unaffected because
the frontend has a streaming-time fallback that pulls ``file_path`` straight
off the ``ToolUseBlock``.  Files created by Bash have no such fallback — they
are only visible to the UI via the backend's ``TurnMetrics.changed_files``.
This test therefore uses Bash specifically to exercise the broken code path.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _start_worktree_task(page: Page, prompt: str) -> PlaywrightTaskPage:
    """Create a WORKTREE-mode workspace and send ``prompt`` as the first message.

    Worktree mode is the default; no mode-selector interaction is needed.
    """
    open_new_workspace_form(page)
    add_workspace_page = PlaywrightAddWorkspacePage(page=page)
    add_workspace_page.get_workspace_name_input().fill("Worktree Bash Test")

    branch_input = add_workspace_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).not_to_have_value("")

    # Clear the empty-first-run prompt prefill (`/sculptor:help`) so the first agent is
    # created promptless — otherwise it runs an extra turn with the default model and the
    # message-count assertions below count those extra messages.
    add_workspace_page.get_task_input().fill("")

    add_workspace_page.submit_and_wait_for_chat_panel()

    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    chat_input = chat_panel.get_chat_input()
    chat_input.focus()

    type_into_tiptap(page, chat_input, prompt)
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
    expect(chat_input).to_have_text("")

    expect(chat_panel.get_messages().nth(1), "agent reply to appear").to_be_attached()
    expect(chat_panel.get_thinking_indicator(), "to finish outputting data").not_to_be_visible()

    return task_page


@user_story("to see a Bash-created file in the turn footer of a worktree workspace")
def test_turn_footer_shows_bash_created_file_in_worktree_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """In a WORKTREE workspace, a file created by Bash must appear in the turn footer.

    Reproduces the bug where ``cp .git/index`` failed in worktrees (where
    ``.git`` is a gitfile), so the backend reported an empty ``changed_files``
    list and the turn footer's file count chip never rendered.
    """
    page = sculptor_instance_.page

    task_page = _start_worktree_task(
        page=page,
        prompt='fake_claude:bash `{"command": "echo hello > bash_created_file.txt"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    turn_footers = alpha_view.get_turn_footers()
    expect(turn_footers.first).to_be_visible()
    expect(turn_footers.first).to_contain_text("1 file")
