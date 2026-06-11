"""Integration tests for the new-workspace modal.

Tests verify:
- Form draft persistence (workspace name) across close/reopen
- Creating a workspace without a prompt (agent in waiting state)
- Keyboard shortcuts: Cmd+I focuses workspace name input
- Arrow key focus recovery when nothing is focused
- Cmd+Enter in the workspace name input submits the form
- Deleting a project also deletes its workspaces
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import ensure_terminal_visible
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to not lose my workspace form entries when I close the modal and reopen it")
def test_workspace_form_draft_persists_after_navigation(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Workspace name draft should survive closing and reopening the modal.

    The modal's draft atoms are not cleared on close — they reset only on
    successful submit — so a half-filled form survives a Cancel/Escape
    so the user can come back to it without retyping.

    Steps:
    1. Create an initial workspace so we're on a workspace page
    2. Open the new-workspace modal via the topbar "+"
    3. Fill in the workspace name (the draft)
    4. Press Escape to close the modal
    5. Open the modal again via the topbar "+"
    6. Verify the workspace name is still populated
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace so we end up on a workspace page (not /home).
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Setup task",
        workspace_name="Initial Workspace",
    )

    # Step 2: Open the modal via the topbar "+".
    add_workspace_button = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_BUTTON)
    expect(add_workspace_button).to_be_visible()
    add_workspace_button.click()

    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_visible()

    # Step 3: Fill in the workspace name (the draft).
    draft_workspace_name = "My Draft Workspace"
    workspace_name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    workspace_name_input.fill(draft_workspace_name)

    # Step 4: Close the modal with Escape (no Submit). The draft atoms are
    # left untouched so the next open shows them again.
    page.keyboard.press("Escape")
    expect(submit_button).to_be_hidden()

    # Step 5: Reopen the modal via the topbar "+".
    add_workspace_button.click()
    expect(submit_button).to_be_visible()

    # Step 6: Verify the workspace name is still populated.
    workspace_name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    expect(workspace_name_input).to_have_value(draft_workspace_name)


# Multi-tab independent-draft testing was removed with the migration from
# ``/ws/new/<draftId>`` (one route per pseudo-tab) to a single shared modal.
# The modal now owns one set of draft atoms; "draft per tab" is no longer
# an expressible concept. The remaining draft test
# (``test_workspace_form_draft_persists_after_navigation``) covers the
# replacement behavior — drafts surviving close/reopen of the modal.


# The "no extra tab flash" test was removed with the modal migration. Its
# premise — that an existing new-workspace pseudo-tab gets atomically
# replaced by the real workspace tab on submit — is no longer expressible:
# the modal flow has no pseudo-tab in the tab bar, so creating a workspace
# always *adds* a tab (count goes from N to N+1) instead of swapping one.


@user_story("to create a workspace and fill in the prompt later")
def test_create_workspace_without_prompt(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Creating a workspace without a prompt should produce a waiting agent that responds to messages.

    Steps:
    1. Create a workspace with only a name (no prompt)
    2. Verify the chat panel appears (agent in waiting state)
    3. Select the Fake Claude model in the chat panel
    4. Send a message to the waiting agent
    5. Verify the agent responds
    """
    page = sculptor_instance_.page

    # Step 1: Create a workspace without a prompt.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Prompt-less Workspace",
    )

    # Step 2: Verify the chat panel appears.
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible()

    # Step 3: Select the Fake Claude model so the agent can respond deterministically.
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)

    # Step 4: Send a message to the waiting agent.
    send_chat_message(chat_panel, "Hello, are you there?")

    # Step 5: Verify the agent responds (1 user message + 1 assistant response).
    wait_for_completed_message_count(chat_panel, expected_message_count=2)


# ---------------------------------------------------------------------------
# Focus management tests
# ---------------------------------------------------------------------------


@user_story("to start typing immediately after creating a workspace")
def test_chat_input_focused_after_workspace_creation(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After creating a workspace, the chat input should have focus so the user can type immediately.

    This test covers three scenarios:
    1. Creating the very first workspace (initial page load)
    2. Creating a second workspace via the "+" button (switching from an existing workspace)
    3. Creating a workspace while the terminal panel is open (terminal must not steal focus)

    All should end with focus in the chat input.
    """
    page = sculptor_instance_.page

    # Scenario 1: Create the first workspace.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="First Workspace",
    )

    chat_editable = page.get_by_test_id(ElementIDs.CHAT_INPUT)
    expect(chat_editable).to_be_focused()

    # Scenario 2: Create a second workspace via the "+" button.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Second Workspace",
    )

    chat_editable = page.get_by_test_id(ElementIDs.CHAT_INPUT)
    expect(chat_editable).to_be_focused()

    # Scenario 3: Ensure the terminal panel is open, then create another workspace.
    # The terminal must not steal focus from the chat input.
    ensure_terminal_visible(page)

    # Verify the terminal panel is visible.
    add_terminal_button = page.get_by_test_id(ElementIDs.ADD_TERMINAL_BUTTON)
    expect(add_terminal_button).to_be_visible()

    # Create a third workspace with the terminal panel open.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Third Workspace (Terminal Open)",
    )

    chat_editable = page.get_by_test_id(ElementIDs.CHAT_INPUT)
    expect(chat_editable).to_be_focused()


@user_story("to press Cmd+I and have the primary prompt input focused on any page")
def test_cmd_i_focuses_prompt_input(sculptor_instance_: SculptorInstance) -> None:
    """Cmd+I should focus the workspace name in the new-workspace modal and the chat input on workspace pages.

    Steps:
    1. In the new-workspace modal, click elsewhere to blur, then press Cmd+I — verify workspace name is focused.
    2. Create a workspace to navigate to a workspace page.
    3. Press Cmd+I — verify the chat input is focused.
    """
    page = sculptor_instance_.page
    mod_key = get_playwright_modifier_key()

    # Step 1: Open the new-workspace modal, blur all inputs, then press Cmd+I.
    navigate_to_add_workspace_page(page)
    name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    expect(name_input).to_be_visible()
    blur_active_element(page)
    expect(name_input).not_to_be_focused()
    page.keyboard.press(f"{mod_key}+i")
    expect(name_input).to_be_focused()

    # Step 2: Create a workspace to navigate to a workspace page.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Cmd+I test workspace",
        workspace_name="Cmd+I Test",
    )

    # Step 3: Blur the chat input, then press Cmd+I — the chat input should be focused.
    chat_editable = page.get_by_test_id(ElementIDs.CHAT_INPUT)
    expect(chat_editable).to_be_visible()
    blur_active_element(page)
    expect(chat_editable).not_to_be_focused()
    page.keyboard.press(f"{mod_key}+i")
    expect(chat_editable).to_be_focused()


@user_story("to regain keyboard control by pressing arrow keys when nothing is focused")
def test_arrow_down_focuses_name_input_when_nothing_focused(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing ArrowDown when no element has focus should focus the workspace name input."""
    page = sculptor_instance_.page

    navigate_to_add_workspace_page(page)
    name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    expect(name_input).to_be_visible()

    blur_active_element(page)
    expect(name_input).not_to_be_focused()

    page.keyboard.press("ArrowDown")
    expect(name_input).to_be_focused()


@user_story("to regain keyboard control by pressing arrow keys when nothing is focused")
def test_arrow_up_focuses_name_input_when_nothing_focused(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing ArrowUp when no element has focus should focus the workspace name input."""
    page = sculptor_instance_.page

    navigate_to_add_workspace_page(page)
    name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    expect(name_input).to_be_visible()

    blur_active_element(page)
    expect(name_input).not_to_be_focused()

    page.keyboard.press("ArrowUp")
    expect(name_input).to_be_focused()


@user_story("to create a workspace by pressing Cmd+Enter while the workspace name input is focused")
def test_cmd_enter_in_workspace_name_creates_workspace(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Pressing Cmd+Enter while focus is in the workspace name input should create the workspace."""
    page = sculptor_instance_.page
    mod_key = get_playwright_modifier_key()

    navigate_to_add_workspace_page(page)
    name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    expect(name_input).to_be_visible()

    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_enabled()

    name_input.fill("Cmd Enter Test")
    name_input.click()
    expect(name_input).to_be_focused()

    page.keyboard.press(f"{mod_key}+Enter")

    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).to_be_visible()


# ---------------------------------------------------------------------------
# Workspace cleanup on project deletion
# ---------------------------------------------------------------------------


def _extract_workspace_id(url: str) -> str:
    """Extract the workspace ID from a Sculptor URL (format: /ws/{workspaceID}/agent/...)."""
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    if not match:
        raise ValueError(f"Could not extract workspace ID from URL: {url}")
    return match.group(1)


@user_story("to have workspaces cleaned up when I delete a project")
def test_deleting_project_also_deletes_its_workspaces(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Deleting a project should also soft-delete all workspaces belonging to it."""
    with sculptor_instance_factory_.spawn_instance() as sculptor_instance:
        page = sculptor_instance.page

        start_task_and_wait_for_ready(
            sculptor_page=page,
            prompt="Setup task",
            workspace_name="Workspace To Delete",
        )

        workspace_id = _extract_workspace_id(page.url)
        base_url = page.url.split("#")[0].rstrip("/")

        get_response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert get_response.ok, f"Expected workspace {workspace_id} to exist, got status {get_response.status}"

        settings_page = navigate_to_settings_page(page=page)
        settings_page.click_on_repositories()

        # Delete the first repo row (the original project).
        repo_rows = page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW)
        expect(repo_rows.first).to_be_visible()
        repo_rows.first.get_by_test_id(ElementIDs.SETTINGS_REMOVE_REPO_BUTTON).click()

        confirm_button = page.get_by_test_id(ElementIDs.SETTINGS_REMOVE_REPO_CONFIRM)
        expect(confirm_button).to_be_visible()
        confirm_button.click()

        # Confirm the delete-confirm dialog dismissed (request submitted) before
        # asserting the resulting state — the dialog stays open while the
        # request is in flight, so checking it disappears is the cleanest
        # before/after signal.
        expect(confirm_button).to_be_hidden()
        # Then wait for the repo row count to drop to zero.
        expect(page.get_by_test_id(ElementIDs.SETTINGS_REPO_ROW)).to_have_count(0)

        get_response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert get_response.status == 404, (
            f"Expected workspace {workspace_id} to be deleted (404) after project deletion, but got status {get_response.status}"
        )
