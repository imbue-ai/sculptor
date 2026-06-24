"""Integration tests for multi-repo functionality.

These tests verify that Sculptor correctly handles:
- Creating new repos through the AddWorkspacePage RepoSelector
- Selecting different repos when creating workspaces
- Running workspaces in different repos and switching between them
- Message isolation across workspaces in different repos
- Repo validation: non-git directories, empty repos, duplicate repos
"""

import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.testing.user_stories import user_story


def _add_repo_via_settings(page: Page, repo_path: Path) -> None:
    """Add a repository via the Settings > Repositories UI dialog."""
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()
    repos_section.add_repo(str(repo_path.resolve()))


@user_story("to create new projects and use them in workspaces")
def test_create_new_project_from_add_workspace_page(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """Test creating a new project via API and using it when creating a workspace.

    Verifies:
    - A project can be added via the API
    - The project selector shows the new project
    - A workspace can be created in the new project
    """
    other_project_name = "other project"
    other_branch_name = "other-branch"

    repo = test_repo_factory_.create_repo(name=other_project_name, branch=other_branch_name)
    page = sculptor_instance_.page

    # Add the repo via the Settings UI
    _add_repo_via_settings(page, repo.base_path)

    # Navigate to the AddWorkspacePage so the UI picks up the new project
    navigate_to_add_workspace_page(page)
    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    expect(add_ws_page.get_submit_button()).to_be_visible()

    # Verify the new project is selectable in the project selector dropdown
    add_ws_page.select_project_by_name(other_project_name)

    # Create a workspace in the new project
    task_page = start_task_and_wait_for_ready(page, prompt="hello world", workspace_name="New Project Workspace")

    # Verify the chat panel is visible (workspace was created successfully)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible()


@user_story("to initialize git in non-git directories")
def test_git_init_dialog_for_non_git_directories(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Test git initialization dialog for non-git directories.

    Verifies:
    - Non-git directories trigger the git init dialog
    - User can choose to initialize git
    - Project loads successfully after git init
    """

    project_name = "non_git_project"
    non_git_dir = tmp_path / project_name
    non_git_dir.mkdir(parents=True, exist_ok=True)

    page = sculptor_instance_.page

    # Navigate to the AddWorkspacePage
    navigate_to_add_workspace_page(page)
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Open the project selector and click "Open New Repo"
    add_ws_page.get_project_selector().click()
    add_ws_page.get_open_new_repo_button().click()

    # Fill in the non-git directory path
    add_repo_dialog = add_ws_page.get_add_repo_dialog()
    expect(add_repo_dialog).to_be_visible()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill(str(non_git_dir))
    # Dismiss the autocomplete dropdown, then submit
    path_input.press("Escape")
    path_input.press("Enter")

    # Git init dialog should appear
    git_init_dialog = add_ws_page.get_git_init_dialog()
    expect(git_init_dialog).to_be_visible()

    # Confirm git init
    git_init_dialog.get_confirm_button().click()

    # Wait for the git init dialog to close and the AddWorkspacePage to be ready
    expect(git_init_dialog).to_be_hidden()
    expect(add_ws_page.get_submit_button()).to_be_visible()

    # Verify the project appears in the project selector
    add_ws_page.get_project_selector().click()
    project_option = add_ws_page.get_project_options().filter(has_text=project_name)
    expect(project_option).to_be_visible()
    page.keyboard.press("Escape")


@user_story("to create workspaces in different projects and switch between them")
def test_create_workspaces_in_multiple_projects_and_switch(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """Test creating workspaces in different projects and navigating between them.

    Verifies:
    - Workspaces can be created in different projects
    - Workspace tabs appear for each workspace
    - Clicking a workspace tab navigates to that workspace's chat
    - Each workspace has its own isolated chat panel
    """
    project_a = "project_alpha"
    project_b = "project_beta"
    branch_a = "alpha-branch"
    branch_b = "beta-branch"

    repo_a = test_repo_factory_.create_repo(name=project_a, branch=branch_a)
    repo_b = test_repo_factory_.create_repo(name=project_b, branch=branch_b)

    page = sculptor_instance_.page

    # Add both repos via the Settings UI
    _add_repo_via_settings(page, repo_a.base_path)
    _add_repo_via_settings(page, repo_b.base_path)

    # Create a workspace in project A
    navigate_to_add_workspace_page(page)
    PlaywrightAddWorkspacePage(page=page).select_project_by_name(project_a)
    task_page_a = start_task_and_wait_for_ready(page, prompt="Alpha task 1", workspace_name="Alpha Workspace")
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    # Create a workspace in project B
    navigate_to_add_workspace_page(page)
    PlaywrightAddWorkspacePage(page=page).select_project_by_name(project_b)
    task_page_b = start_task_and_wait_for_ready(page, prompt="Beta task 1", workspace_name="Beta Workspace")
    chat_panel_b = task_page_b.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=2)

    # Verify there are 2 workspace rows
    expect(get_workspace_sidebar(page).get_workspace_rows()).to_have_count(2)

    # Click the Alpha workspace row to switch back (sidebar rows sort by name)
    navigate_to_workspace(page, "Alpha Workspace")
    task_page = PlaywrightTaskPage(page=page)
    expect(task_page.get_chat_panel()).to_be_visible()

    # Click the Beta workspace row to switch
    navigate_to_workspace(page, "Beta Workspace")
    expect(task_page.get_chat_panel()).to_be_visible()


@user_story("to send messages across workspaces in multiple projects")
def test_send_messages_across_multiple_project_workspaces(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """Test sending messages in workspaces across different projects.

    Verifies:
    - Messages can be sent in workspaces using different projects
    - Message history is preserved when switching between workspace tabs
    - No message cross-contamination between workspaces
    """
    project_a = "project_alpha"
    project_b = "project_beta"
    branch_a = "alpha-branch"
    branch_b = "beta-branch"

    initial_prompt_b = "hello from project B"
    follow_up_prompt_b = "hello again from B"

    initial_prompt_a = "hello from project A"
    follow_up_prompt_a = "hello again from A"

    repo_a = test_repo_factory_.create_repo(name=project_a, branch=branch_a)
    repo_b = test_repo_factory_.create_repo(name=project_b, branch=branch_b)

    page = sculptor_instance_.page

    # Add both repos via the Settings UI
    _add_repo_via_settings(page, repo_a.base_path)
    _add_repo_via_settings(page, repo_b.base_path)

    # Create workspace in project A
    navigate_to_add_workspace_page(page)
    PlaywrightAddWorkspacePage(page=page).select_project_by_name(project_a)
    task_page_a = start_task_and_wait_for_ready(page, prompt=initial_prompt_a, workspace_name="Alpha Workspace")
    chat_panel_a = task_page_a.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=2)

    # Send follow-up in workspace A
    send_chat_message(chat_panel=chat_panel_a, message=follow_up_prompt_a)
    wait_for_completed_message_count(chat_panel=chat_panel_a, expected_message_count=4)

    # Create workspace in project B
    navigate_to_add_workspace_page(page)
    PlaywrightAddWorkspacePage(page=page).select_project_by_name(project_b)
    task_page_b = start_task_and_wait_for_ready(page, prompt=initial_prompt_b, workspace_name="Beta Workspace")
    chat_panel_b = task_page_b.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=2)

    # Send follow-up in workspace B
    send_chat_message(chat_panel=chat_panel_b, message=follow_up_prompt_b)
    wait_for_completed_message_count(chat_panel=chat_panel_b, expected_message_count=4)

    # Switch back to workspace A via its sidebar row
    navigate_to_workspace(page, "Alpha Workspace")

    # Re-acquire the chat panel after navigation
    chat_panel_a = PlaywrightTaskPage(page=page).get_chat_panel()
    expect(chat_panel_a._locator).to_be_visible()

    # Verify workspace A still has 4 messages (2 user + 2 assistant).
    expect(chat_panel_a.get_messages()).to_have_count(4)

    # Switch back to workspace B
    navigate_to_workspace(page, "Beta Workspace")
    chat_panel_b = PlaywrightTaskPage(page=page).get_chat_panel()
    expect(chat_panel_b._locator).to_be_visible()

    # Verify workspace B still has 4 messages
    expect(chat_panel_b.get_messages()).to_have_count(4)


@user_story("to have the most recently used project pre-selected when creating a new workspace")
def test_mru_project_updates_after_creating_workspace(
    sculptor_instance_: SculptorInstance, test_repo_factory_: TestRepoFactory
) -> None:
    """Creating a workspace should update the MRU project so the Add Workspace page defaults to it.

    The initial project (project A) is set up by the test fixture. We add a second
    project (project B) — which sets B as MRU via activate_project — then create a
    workspace in project A. After navigating to the Add Workspace page, project A
    should be pre-selected because it was most recently *used*, not project B.

    Steps:
    1. Add a second project (project B) — this sets MRU to B via activate_project
    2. Create a workspace in the original project (project A)
    3. Navigate to the Add Workspace page
    4. Verify that the project selector shows project A (the most recently used project)
    """
    project_b_name = "project_bravo"
    repo_b = test_repo_factory_.create_repo(name=project_b_name, branch="bravo-branch")

    page = sculptor_instance_.page
    project_a_name = sculptor_instance_.project_path.name

    # Step 1: Add project B via Settings UI. This calls activate_project which sets MRU to B.
    _add_repo_via_settings(page, repo_b.base_path)

    # Step 2: Create a workspace in the original project A (not B).
    # The project selector should still show A since it's the first project.
    navigate_to_add_workspace_page(page)
    PlaywrightAddWorkspacePage(page=page).select_project_by_name(project_a_name)
    start_task_and_wait_for_ready(page, prompt="Alpha task", workspace_name="Alpha Workspace")

    # Step 3: Navigate back to the Add Workspace page.
    navigate_to_add_workspace_page(page)

    # Step 4: Verify the project selector shows project A (not B) as the default,
    # because we most recently created a workspace in project A.
    add_ws_page = PlaywrightAddWorkspacePage(page=page)
    expect(add_ws_page.get_project_selector()).to_contain_text(project_a_name)


@pytest.mark.skip(reason="Duplicate project name disambiguation requires redesign for workspace-tabs UI")
@user_story("to distinguish between projects with the same folder name")
def test_duplicate_project_names() -> None:
    """Test handling of projects with same leaf folder names but different paths."""


@user_story("to create an initial commit when adding an empty git repo")
def test_empty_repo_initial_commit_dialog(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Test that adding a git repo with no commits shows the initial commit dialog.

    Verifies:
    - An empty git repo (initialized but no commits) triggers the validation dialog
    - The dialog offers to make an initial commit
    - After confirming, the repo is added successfully
    """
    repo_name = "empty_git_repo"
    empty_repo_dir = tmp_path / repo_name
    empty_repo_dir.mkdir(parents=True, exist_ok=True)

    # Initialize git but make no commits
    subprocess.run(["git", "init"], cwd=empty_repo_dir, check=True, capture_output=True)

    page = sculptor_instance_.page

    # Add the empty repo via Settings > Repositories
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()

    # Click the "Add repository" button and fill the path
    add_repo_dialog = repos_section.open_add_repo_dialog()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill(str(empty_repo_dir))
    path_input.press("Escape")
    path_input.press("Enter")

    # The validation dialog should appear with the initial commit prompt
    git_init_dialog = settings_page.get_git_init_dialog()
    expect(git_init_dialog).to_be_visible()
    expect(git_init_dialog).to_contain_text("no commits")

    # Click "Make Initial Commit"
    git_init_dialog.get_initial_commit_confirm_button().click()

    # The dialog should close and the repo should be added
    expect(git_init_dialog).to_be_hidden()

    # Verify the repo appears in the repositories list
    expect(repos_section.get_repo_rows().filter(has_text=repo_name)).to_be_visible()


@user_story("to see an error when adding a repo that is already registered")
def test_adding_duplicate_repo_shows_error(sculptor_instance_: SculptorInstance) -> None:
    """Test that adding a repo that's already registered shows an error.

    Verifies:
    - Adding a repo path that is already registered triggers a validation error
    - The error message indicates the repo is already added
    """
    page = sculptor_instance_.page

    # The sculptor_instance_ fixture already has a repo registered.
    # Get its path from the Settings > Repositories page.
    existing_repo_path = str(sculptor_instance_.project_path.resolve())

    # Try to add the same repo again via Settings > Repositories
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()

    add_repo_dialog = repos_section.open_add_repo_dialog()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill(existing_repo_path)

    # Wait for the autocomplete dropdown to open before dismissing it.
    # Otherwise the dropdown can open in the gap between Escape and Enter, and
    # Enter ends up selecting the highlighted item instead of submitting.
    expect(add_repo_dialog.get_path_autocomplete_items().first).to_be_visible()

    path_input.press("Escape")
    path_input.press("Enter")

    # The validation dialog should appear with an error about the repo already existing
    validation_dialog = settings_page.get_git_init_dialog()
    expect(validation_dialog).to_be_visible()
    expect(validation_dialog).to_contain_text("already")
