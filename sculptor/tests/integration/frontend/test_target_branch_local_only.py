"""Regression test for the Changes tab on a local-only repo with no remotes.

Two related bugs:

1. The "All" sub-tab is missing on WORKTREE workspaces created from a
   local-only source repo. ``_resolve_default_target_branch`` only falls
   back to the local ``main``/``master`` ref for CLONE workspaces, so
   WORKTREE leaves ``target_branch=None`` and ``DiffScopePicker`` hides
   the "All" item.

2. The Uncommitted tab shows "No changes" even after the agent has
   written a new file into the worktree. The diff pipeline should
   surface untracked files via the ``git ls-files --others`` step.

Both should work for a worktree workspace created from a local-only repo
(the user-reported repro: ``~/code/builder``).
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""


@user_story("to see uncommitted changes and the All tab on a worktree workspace from a local-only repo")
def test_worktree_on_local_only_repo_shows_all_tab_and_uncommitted_changes(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A WORKTREE workspace on a local-only repo (no remotes) should still
    show both the "All" sub-tab and the agent's uncommitted file.

    The default test repo built by ``MockRepoState.build_locally`` has no
    remotes — so it matches the user's ``~/code/builder`` scenario.

    Worktree mode is the default; no mode-selector interaction needed.
    """
    page = sculptor_instance_.page

    navigate_to_add_workspace_page(page)
    add_workspace_page = PlaywrightAddWorkspacePage(page=page)
    add_workspace_page.get_workspace_name_input().fill("Local only worktree")

    # Branch-name input auto-fills; just wait for it to settle.
    branch_input = add_workspace_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).not_to_have_value("")

    add_workspace_page.submit_and_wait_for_chat_panel()

    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    send_chat_message(chat_panel=chat_panel, message=_WRITE_FILE_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    task_page.activate_changes_panel(scope="uncommitted")

    # Bug 1: The "All" scope button must be present for a local-only repo
    # once the target_branch fallback resolves to a local main/master.
    changes_panel = task_page.get_changes_panel()
    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_be_visible()

    # Bug 2: The Uncommitted tab must list the file the agent just wrote.
    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.filter(has_text="hello.py")).to_be_visible()
