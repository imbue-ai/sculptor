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

from sculptor.constants import ElementIDs
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import soft_reload_page
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

    # Soft-reload so the branch selector picks up the newly created branch
    # (direct page reload causes ERR_INSUFFICIENT_RESOURCES on CI). After
    # the reload we land on /home with the modal closed, so open the
    # new-workspace modal explicitly before filling the form.
    soft_reload_page(page)
    navigate_to_add_workspace_page(page)
    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_visible()

    # Fill in the workspace name (required field)
    page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT).fill("Feature branch workspace")

    # Override the auto-filled branch name so we know exactly what the
    # workspace's branch will be.
    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    branch_input.fill(workspace_branch)
    expect(branch_input).to_have_value(workspace_branch)

    # Select feature_branch via the branch selector (the source to clone from)
    branch_selector = page.get_by_test_id(ElementIDs.BRANCH_SELECTOR)
    branch_selector.click()
    branch_option = (
        page.get_by_test_id(ElementIDs.BRANCH_OPTION).filter(has_text=feature_branch).filter(has_not_text="*")
    )
    expect(branch_option).to_have_count(1, timeout=30_000)
    branch_option.click()

    # Wait for the selector's displayed value to reflect the click before
    # submitting — without this, submit can fire before React commits the
    # `userSelectedBranch` state update and the request goes out with the
    # project's current branch instead of `feature_branch`.
    expect(branch_selector).to_contain_text(feature_branch)

    # Submit to create the workspace (no prompt on the Add Workspace page)
    expect(submit_button).to_be_enabled()
    submit_button.click()

    # Wait for the chat panel to appear (we navigated to the workspace/agent page)
    chat_panel_locator = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel_locator).to_be_visible(timeout=30000)

    # Clone mode should not show a mode badge (no experimental flags enabled)
    mode_badge = page.get_by_test_id(ElementIDs.TASK_MODE_BADGE)
    expect(mode_badge).not_to_be_visible()

    # Install a clipboard interceptor so we can read what was written
    install_clipboard_interceptor(page)

    # Wait for the branch name to load in the workspace banner (async, can take 1-2s)
    # and click it to copy the value to the clipboard.
    branch_element = page.get_by_test_id(ElementIDs.BRANCH_NAME)
    expect(branch_element).to_be_visible(timeout=10000)
    expect(branch_element).to_have_text(workspace_branch)
    branch_element.click()

    # Read what was written to the clipboard
    clipboard_value = read_intercepted_clipboard(page)

    assert clipboard_value == workspace_branch, (
        f"Expected clipboard to contain '{workspace_branch}', got '{clipboard_value}'"
    )
