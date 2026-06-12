"""Regression test: new agents should inherit the model from the workspace's existing agent.

In an existing workspace, changing the model and sending a prompt, then
creating a new agent via the "+" button, should cause the new agent to
inherit the model from the first agent. Previously the frontend sent no
model when creating a new agent and the backend fell back to CLAUDE_4_OPUS.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_2_MODEL_NAME
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to have new agents inherit the model from the workspace's existing agent")
def test_new_agent_inherits_model_from_existing_agent(
    sculptor_instance_: SculptorInstance,
) -> None:
    """New agents should inherit the model from the workspace's existing agent.

    Steps:
    1. Create a workspace with a prompt using "Fake Claude"
    2. Change the model to "Fake Claude 2" and send a message
    3. Click "+" to add a new agent
    4. Verify the new agent's model selector shows "Fake Claude 2"
    """
    page = sculptor_instance_.page

    # Create workspace with a prompt using Fake Claude
    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Hello from agent 1"}`',
        model_name=FAKE_CLAUDE_MODEL_NAME,
        workspace_name="Model Inherit WS",
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Change the model to "Fake Claude 2" and send a message
    select_model_by_name(chat_panel, FAKE_CLAUDE_2_MODEL_NAME)
    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:text `{"text": "Now using Fake Claude 2"}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Verify agent 1's model selector shows "Fake Claude 2"
    model_selector = chat_panel.get_model_selector()
    expect(model_selector).to_have_text(FAKE_CLAUDE_2_MODEL_NAME)

    # Add a new agent via the "+" button
    agent_tab_bar = task_page.get_agent_tab_bar()
    add_agent_button = agent_tab_bar.get_add_agent_button()
    expect(add_agent_button).to_be_visible()
    add_agent_button.click()

    # Wait for the second agent tab to appear
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(2)

    # The new agent's model selector should show "Fake Claude 2" (inherited)
    task_page_2 = PlaywrightTaskPage(page=page)
    chat_panel_2 = task_page_2.get_chat_panel()
    new_agent_model_selector = chat_panel_2.get_model_selector()
    expect(new_agent_model_selector).to_have_text(FAKE_CLAUDE_2_MODEL_NAME)
