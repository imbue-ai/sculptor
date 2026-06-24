"""Regression test for two agents streaming concurrently (AGENT-05).

Two agents — one in the center section, one in the right section — each driven by a
streaming FakeClaude task should update independently: neither blocks, drops, nor
overwrites the other's content or status dot.

This is a NEW regression test (no pre-rewrite analog). It is currently skipped: it
depends on rendering an agent in a NON-center section at the same time as the center
agent, which needs the drag / move-to-section affordance (Task 4.1) — new agents
always land in center today and there is no UI to relocate one to the right.

The scaffolding helper below (create two agents, drive both) is the net-new test
territory the plan calls for — NOT a new FakeClaude verb. It is retained so the
regression lands intact the moment the placement affordance is wired.
"""

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_CONCURRENT_SKIP_REASON = "Concurrent center+right streaming (AGENT-05) needs an agent rendered in the right section alongside the center agent, which requires the drag / move-to-section affordance not wired until Task 4.1."

_STREAM_PROMPT = 'fake_claude:text `{"text": "streaming response from this agent"}`'


def _create_two_agents(page: Page) -> tuple[str, str]:
    """Create a workspace with one agent, then add a second; return both panel ids.

    Net-new scaffolding for the two-agent regression (not a FakeClaude verb): the
    first agent comes from the workspace-create flow, the second from the `+`
    add-panel dropdown. Both land in center today; Task 4.1's move affordance is
    what lets the second be relocated to the right for the concurrent assertion.
    """
    task_page = PlaywrightTaskPage(page=page)
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt=_STREAM_PROMPT, workspace_name="Concurrent WS")
    first_panel_id = f"agent:{task_page.get_task_id()}"

    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(2)
    second_panel_id = f"agent:{task_page.get_task_id()}"
    return first_panel_id, second_panel_id


@pytest.mark.skip(reason=_CONCURRENT_SKIP_REASON)
@user_story("to run two agents streaming at once without one blocking the other")
def test_two_agents_stream_independently(sculptor_instance_: SculptorInstance) -> None:
    """Two agents (center + right) stream concurrently and update independently.

    Placeholder for AGENT-05 until the move-to-section affordance (Task 4.1) lands.
    The intended flow: create two agents, relocate the second to the right section,
    drive a streaming prompt into each, and assert both chats reach their completed
    message counts without one stalling the other.
    """
    page = sculptor_instance_.page
    first_panel_id, second_panel_id = _create_two_agents(page)
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    # (Once Task 4.1 lands: move second_panel_id to the right section here.)

    task_page = PlaywrightTaskPage(page=page)
    panel_tabs.get_panel_tab(second_panel_id).click()
    chat_panel = task_page.get_chat_panel()
    send_chat_message(chat_panel=chat_panel, message=_STREAM_PROMPT)

    panel_tabs.get_panel_tab(first_panel_id).click()
    first_chat = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=first_chat, expected_message_count=2)
