"""Regression test: Copy Branch Name should copy the workspace's branch, not the project repo branch.

Bug: When a workspace is created in clone mode on a non-default branch, the workspace
banner correctly displays the workspace's branch name, but clicking the branch name
to copy it copies the project-level repo branch instead.

Root cause: The copy mechanism uses the project repo branch instead of the workspace's
working directory branch (useWorkspaceBranch) to determine the branch name.

Note: CLONE workspaces now always create their own branch (the requestedBranchName
auto-fill from the New Workspace form), so the workspace's branch differs from the
selected source branch. The test sets an explicit branch name so the expected value
is deterministic.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to copy a workspace's branch name and get the correct branch")
def test_copy_branch_name_copies_workspace_branch(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the branch name in the workspace banner should copy the workspace's actual branch.

    Steps:
    1. Create a second branch (feature_branch) in the test repo to use as the clone source
    2. Switch the project repo back to the default branch (testing)
    3. Create a workspace in clone mode off feature_branch, with an explicit
       new-branch name "copy-branch-name-test"
    4. Wait for the workspace to be ready
    5. Verify the workspace banner displays the new branch (not "testing")
    6. Click the branch name to copy
    7. Assert the clipboard contains the new branch (not "testing")
    """
    feature_branch = "feature_branch"
    workspace_branch = "copy-branch-name-test"
    page = sculptor_instance_.page

    # Create a feature branch with a commit so it's selectable
    sculptor_instance_.repo.create_reset_and_checkout_branch(feature_branch)
    sculptor_instance_.repo.write_file("src/feature.py", "print('feature')")
    sculptor_instance_.repo.stage_all_changes()
    sculptor_instance_.repo.commit("Add feature file", commit_time="2025-01-01T00:00:02")

    # Switch back to the default branch so the project repo is on a different branch
    sculptor_instance_.repo.checkout_branch("testing")

    # Bring up the new-workspace form (per-test cleanup deletes all workspaces
    # and dismisses the first-run offer, so nothing is open yet). The form
    # re-sources the repo's branches on every open, so the branch created
    # above is selectable without reloading the SPA.
    open_new_workspace_form(page)
    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    expect(add_ws_page.get_submit_button()).to_be_visible()

    # Fill in the workspace name (required field)
    add_ws_page.get_workspace_name_input().fill("Feature branch workspace")

    # Override the auto-filled branch name so we know exactly what the
    # workspace's branch will be (the form default is `<user>/<slug>`).
    branch_input = add_ws_page.get_branch_name_input()
    branch_input.fill(workspace_branch)

    # Select feature_branch via the branch selector (the source to clone from)
    add_ws_page.select_branch(feature_branch)

    # Wait for the selector's displayed value to reflect the click before
    # submitting — without this, submit can fire before React commits the
    # `userSelectedBranch` state update and the request goes out with the
    # project's current branch instead of `feature_branch`.
    expect(add_ws_page.get_branch_selector()).to_contain_text(feature_branch)

    # Submit to create the workspace (no prompt on the Add Workspace page)
    add_ws_page.submit_and_wait_for_chat_panel()

    # Clone mode should not show a mode badge (no experimental flags enabled)
    task_page = PlaywrightTaskPage(page=page)
    expect(task_page.get_mode_badge()).not_to_be_visible()

    # Install a clipboard interceptor so we can read what was written
    install_clipboard_interceptor(page)

    # Wait for the branch name to load in the workspace banner (async, can take 1-2s)
    # and click it to copy the value to the clipboard.
    branch_element = task_page.get_branch_name_element()
    expect(branch_element).to_have_text(workspace_branch)
    branch_element.click()

    # Read what was written to the clipboard
    clipboard_value = read_intercepted_clipboard(page)

    assert clipboard_value == workspace_branch, (
        f"Expected clipboard to contain '{workspace_branch}', got '{clipboard_value}'"
    )
