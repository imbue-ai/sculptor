"""Regression test: Cmd+Enter in the Add Repo dialog should not create a workspace.

Bug: On the Add Workspace page ("Name your workspace"), opening the repo selector
and choosing the add-repository option opens a dialog with a path autocomplete.
Pressing Cmd+Enter there is meant to *add the selected repository* and return to
the Add Workspace page. Instead, the page's global "Cmd+Enter creates the
workspace" listener also fired, so a single Cmd+Enter both added the repo and
created a workspace, navigating the user straight through to the agent chat.

The expected behavior is that Cmd+Enter inside the dialog only adds the repo and
leaves the user on the Add Workspace page.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to add a repository with Cmd+Enter without being thrown into a new workspace")
def test_add_repo_cmd_enter_stays_on_add_workspace_page(
    sculptor_instance_: SculptorInstance,
    test_repo_factory_: TestRepoFactory,
) -> None:
    """Cmd+Enter in the Add Repo dialog must only add the repo, not create a workspace.

    Steps:
    1. Create a second git repo to add.
    2. Navigate to the Add Workspace page (a repo is already selected).
    3. Open the repo selector and choose the add-repository option.
    4. Type the new repo's path and press Cmd+Enter.
    5. Verify the repo is added (dialog closes, new repo selected) and we remain
       on the Add Workspace page — no workspace was created and no chat opened.
    """
    page = sculptor_instance_.page

    # Step 1: Create a second git repo to add via the dialog.
    target_repo_name = "cmd-enter-target-repo"
    target_repo = test_repo_factory_.create_repo(name=target_repo_name, branch="main")
    target_repo_path = str(target_repo.base_path.resolve())

    # Step 2: Navigate to the Add Workspace page. This mounts NewWorkspaceForm
    # (and its global Cmd+Enter listener), with the initial project selected.
    navigate_to_add_workspace_page(page)
    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    # Wait until the form is fully ready: the Create workspace button only
    # becomes enabled once the repo info and the branch-name preview have
    # loaded. This is the state in which the page's Cmd+Enter handler would
    # actually create a workspace (it bails early on an empty branch name), so
    # it's required to faithfully reproduce the bug.
    expect(add_ws_page.get_submit_button()).to_be_enabled(timeout=30_000)

    # Step 3: Open the repo selector and choose the add-repository option.
    add_ws_page.get_project_selector().click()
    add_ws_page.get_open_new_repo_button().click()
    add_repo_dialog = add_ws_page.get_add_repo_dialog()
    expect(add_repo_dialog).to_be_visible()

    # Step 4: Type the new repo's path and press Cmd+Enter to add it.
    path_input = add_repo_dialog.get_path_input()
    path_input.fill(target_repo_path)
    path_input.press(f"{get_playwright_modifier_key()}+Enter")

    # The repo is validated and added, so the dialog closes.
    expect(add_repo_dialog).to_be_hidden(timeout=30_000)

    # Regression: Cmd+Enter inside the dialog must ONLY add the repo. Before the
    # fix, the Add Workspace page's global "Cmd+Enter creates the workspace"
    # listener also fired, creating a workspace and navigating to its chat panel.
    # We must instead stay on the Add Workspace page.
    #
    # The Create workspace button is the robust signal: if the bug fired, the
    # form would flip to its pending state (button disabled) and then unmount as
    # the page navigated to the new workspace's chat, so the button would never
    # be enabled here again.
    expect(add_ws_page.get_submit_button()).to_be_enabled(timeout=30_000)
    # The newly added repo is selected on the (still-present) Add Workspace page.
    expect(add_ws_page.get_project_selector()).to_contain_text(target_repo_name)
    # And no workspace chat was ever opened.
    expect(add_ws_page.get_chat_panel()).not_to_be_visible()
