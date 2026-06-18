"""Integration tests for the new-workspace modal.

Tests verify:
- Form draft persistence (workspace name) across close/reopen
- Creating a workspace without a prompt (agent in waiting state)
- Keyboard shortcuts: Cmd+I focuses workspace name input
- Arrow key focus recovery when nothing is focused
- Cmd+Enter in the workspace name input submits the form
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panels import ensure_terminal_visible
from sculptor.testing.elements.panels import get_add_terminal_button
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import blur_active_element
from sculptor.testing.playwright_utils import open_new_workspace_modal
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
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
    modal = PlaywrightNewWorkspaceModalPage(page=page)

    # Step 1: Create a workspace so we end up on a workspace page (not /home).
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="Setup task",
        workspace_name="Initial Workspace",
    )

    # Step 2: Open the modal via the topbar "+".
    add_workspace_button = modal.get_add_workspace_button()
    expect(add_workspace_button).to_be_visible()
    add_workspace_button.click()

    submit_button = modal.get_submit_button()
    expect(submit_button).to_be_visible()

    # Step 3: Fill in the workspace name (the draft).
    draft_workspace_name = "My Draft Workspace"
    workspace_name_input = modal.get_workspace_name_input()
    workspace_name_input.fill(draft_workspace_name)

    # Step 4: Close the modal with Escape (no Submit). The draft atoms are
    # left untouched so the next open shows them again.
    page.keyboard.press("Escape")
    expect(submit_button).to_be_hidden()

    # Step 5: Reopen the modal via the topbar "+".
    add_workspace_button.click()
    expect(submit_button).to_be_visible()

    # Step 6: Verify the workspace name is still populated.
    workspace_name_input = modal.get_workspace_name_input()
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
    task_page = PlaywrightTaskPage(page=page)

    # Scenario 1: Create the first workspace.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="First Workspace",
    )

    chat_editable = task_page.get_chat_panel().get_chat_input()
    expect(chat_editable).to_be_focused()

    # Scenario 2: Create a second workspace via the "+" button.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Second Workspace",
    )

    chat_editable = task_page.get_chat_panel().get_chat_input()
    expect(chat_editable).to_be_focused()

    # Scenario 3: Ensure the terminal panel is open, then create another workspace.
    # The terminal must not steal focus from the chat input.
    ensure_terminal_visible(page)

    # Verify the terminal panel is visible.
    add_terminal_button = get_add_terminal_button(page)
    expect(add_terminal_button).to_be_visible()

    # Create a third workspace with the terminal panel open.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Third Workspace (Terminal Open)",
    )

    chat_editable = task_page.get_chat_panel().get_chat_input()
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
    modal = PlaywrightNewWorkspaceModalPage(page=page)
    task_page = PlaywrightTaskPage(page=page)

    # Step 1: Open the new-workspace modal, blur all inputs, then press Cmd+I.
    open_new_workspace_modal(page)
    name_input = modal.get_workspace_name_input()
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
    chat_editable = task_page.get_chat_panel().get_chat_input()
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
    modal = PlaywrightNewWorkspaceModalPage(page=page)

    open_new_workspace_modal(page)
    name_input = modal.get_workspace_name_input()
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
    modal = PlaywrightNewWorkspaceModalPage(page=page)

    open_new_workspace_modal(page)
    name_input = modal.get_workspace_name_input()
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
    modal = PlaywrightNewWorkspaceModalPage(page=page)

    open_new_workspace_modal(page)
    name_input = modal.get_workspace_name_input()
    expect(name_input).to_be_visible()

    submit_button = modal.get_submit_button()
    expect(submit_button).to_be_enabled()

    name_input.fill("Cmd Enter Test")
    name_input.click()
    expect(name_input).to_be_focused()

    page.keyboard.press(f"{mod_key}+Enter")

    chat_panel = modal.get_chat_panel()
    expect(chat_panel).to_be_visible()
