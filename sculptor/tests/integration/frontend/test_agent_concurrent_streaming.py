"""Regression tests for multi-agent workspaces acting on the right agent (AGENT-05).

Two agents — one in the center section, one in the right section — each driven by a
streaming FakeClaude task should update independently: neither blocks, drops, nor
overwrites the other's content or status dot.

The concurrent-streaming case is a NEW regression test (no pre-rewrite analog). It is
currently skipped: it depends on rendering an agent in a NON-center section at the
same time as the center agent, which needs the drag / move-to-section affordance
(Task 4.1) — new agents always land in center today and there is no UI to relocate
one to the right.

The scaffolding helper below (create two agents, drive both) is the net-new test
territory the plan calls for — NOT a new FakeClaude verb. It is retained so the
regression lands intact the moment the placement affordance is wired.

The panel-vs-route targeting case below needs no relocation: creating a second agent
navigates the route to it, while re-activating the first agent's TAB does not
navigate — so a chat panel can render an agent that is not the route's agent, and
actions inside the panel (Stop) must target the panel's agent.
"""

import re

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

# Long enough to outlast agent creation and tab switching; the test interrupts
# the turn well before the sleep elapses.
_SLEEP_PROMPT = 'fake_claude:sleep `{"seconds": 120}`'


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


@user_story("to stop an agent from its own panel while another agent holds the route")
def test_stop_button_interrupts_the_panels_agent(sculptor_instance_: SculptorInstance) -> None:
    """The Stop button interrupts the PANEL's agent, not the route's agent.

    Start a first agent on a long turn, then create a second agent — creation
    navigates the route to the new agent. Re-activating the first agent's tab
    does NOT navigate, so the route still points at the (idle) second agent
    while the panel renders the busy first one. Clicking Stop in that panel
    must interrupt the first agent; an interrupt aimed at the route's agent
    would be a no-op and leave the first turn running until its sleep elapses.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(
        page,
        prompt=_SLEEP_PROMPT,
        workspace_name="Stop Targets Panel WS",
        wait_for_agent_to_finish=False,
    )
    first_agent_id = task_page.get_task_id()
    first_panel_id = f"agent:{first_agent_id}"
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # The new agent lands in center, becomes the active tab, and takes the
    # route. Wait for the navigation before reading the new agent's id — the
    # tab can render a beat before the URL updates.
    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(2)
    expect(page).not_to_have_url(re.compile(f"/agent/{first_agent_id}$"))
    second_agent_id = task_page.get_task_id()
    assert second_agent_id != first_agent_id

    # Back to the first agent's tab. Tab activation is a layout write, not a
    # navigation — the route (the load-bearing premise) stays on the second agent.
    panel_tabs.get_panel_tab(first_panel_id).click()
    assert task_page.get_task_id() == second_agent_id

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()

    # The panel's agent stops: its turn ends well before the 120s sleep could.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
