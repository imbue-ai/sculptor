"""Integration test for branch switching and workspace creation."""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.elements.user_config import enable_in_place_workspaces
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to create a clone workspace from a different branch using the branch selector")
def test_branch_switching_with_untracked_file(sculptor_instance_: SculptorInstance) -> None:
    """Set up a test repo with branches A and B plus an untracked file, check out
    branch A, start Sculptor, and use the branch selector in the New Workspace
    modal to create a CLONE workspace from branch B.
    """
    page = sculptor_instance_.page

    # Set up test branches
    branch_a = "branch_a"
    branch_b = "branch_b"

    # Create and set up branch A
    sculptor_instance_.repo.create_reset_and_checkout_branch(branch_a)
    sculptor_instance_.repo.write_file("src/file_a.py", "print('Hello from branch A!')")
    sculptor_instance_.repo.stage_all_changes()
    sculptor_instance_.repo.commit("Add file A", commit_time="2025-01-01T00:00:01")

    # Create and set up branch B
    sculptor_instance_.repo.create_reset_and_checkout_branch(branch_b)
    sculptor_instance_.repo.write_file("src/file_b.py", "print('Hello from branch B!')")
    sculptor_instance_.repo.stage_all_changes()
    sculptor_instance_.repo.commit("Add file B", commit_time="2025-01-01T00:00:02")

    # Switch back to branch A (this is our current branch when Sculptor starts)
    sculptor_instance_.repo.checkout_branch(branch_a)

    # Create an untracked file
    sculptor_instance_.repo.write_file("untracked_file.txt", "This is an untracked file")

    # Verify initial state
    current_branch = sculptor_instance_.repo.get_current_branch_name()
    assert current_branch == branch_a, f"Expected to be on {branch_a}, but on {current_branch}"

    # Verify both branches exist
    all_branches = sculptor_instance_.repo.get_branches()
    assert branch_a in all_branches, f"Branch {branch_a} not found in repo. Available branches: {all_branches}"
    assert branch_b in all_branches, f"Branch {branch_b} not found in repo. Available branches: {all_branches}"

    # Clone mode is opt-in — enable it before opening the modal.
    enable_clone_workspaces(page)

    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)
    add_workspace.get_workspace_name_input().fill("Branch B workspace")
    add_workspace.select_clone_mode()

    # Select branch B as the clone source via the branch selector.
    add_workspace.select_branch(branch_b)

    add_workspace.submit_and_wait_for_chat_panel()

    # Switch to the Fake Claude model on the chat panel, then send a prompt.
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    send_chat_message(chat_panel=chat_panel, message="Hello!")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Clone mode shows a "clone" badge on the workspace page.
    mode_badge = page.get_by_test_id(ElementIDs.TASK_MODE_BADGE)
    expect(mode_badge).to_be_visible()
    expect(mode_badge).to_have_text("clone")


@user_story("to see task mode displayed correctly on the workspace page")
def test_in_place_mode_displayed_correctly(sculptor_instance_: SculptorInstance) -> None:
    """Test that in-place mode workspaces display 'In-place' badge on the workspace page."""
    page = sculptor_instance_.page

    # Enable the experimental in-place workspaces flag so the mode selector is visible.
    enable_in_place_workspaces(page)

    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)
    add_workspace.get_workspace_name_input().fill("In-place workspace")
    add_workspace.select_in_place_mode()

    add_workspace.submit_and_wait_for_chat_panel()

    # Switch to the Fake Claude model on the chat panel, then send a prompt.
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    send_chat_message(chat_panel=chat_panel, message="Hello in-place!")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Verify the workspace mode badge shows "in-place"
    mode_badge = page.get_by_test_id(ElementIDs.TASK_MODE_BADGE)
    expect(mode_badge).to_be_visible()
    expect(mode_badge).to_have_text("in-place")
