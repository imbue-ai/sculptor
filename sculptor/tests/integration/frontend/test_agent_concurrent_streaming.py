"""Regression tests for multi-agent workspaces acting on the right agent.

Two agents — one in the center section, one in the right section — each driven by a
streaming FakeClaude task should update independently: neither blocks, drops, nor
overwrites the other's chat content.

The panel-vs-route targeting case below needs no second section: creating a second
agent navigates the route to it, while re-activating the first agent's TAB does not
navigate — so a chat panel can render an agent that is not the route's agent, and
actions inside the panel (Stop) must target the panel's agent.
"""

import json
import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_STREAM_PROMPT = 'fake_claude:text `{"text": "streaming response from this agent"}`'


def _paused_stream_prompt(pause: FakeClaudePause) -> str:
    """A turn that parks on the pause's sentinel, then streams a text response.

    The agent stays busy — with no wall-clock for CI load to race — until the
    test calls ``pause.release()``, at which point the turn finishes with one
    assistant message.
    """
    steps = {
        "steps": [
            {"command": "wait_for_file", "args": {"path": str(pause.release_path)}},
            {"command": "text", "args": {"text": "streaming response from this agent"}},
        ]
    }
    return f"fake_claude:multi_step `{json.dumps(steps)}`"


@user_story("to run two agents streaming at once without one blocking the other")
def test_two_agents_stream_independently(sculptor_instance_: SculptorInstance) -> None:
    """Two agents (center + right) stream concurrently and update independently.

    The first agent comes from the workspace-create flow (center); the second is
    added from the right section's `+` add-panel dropdown, landing it in the right
    section — so both chat panels are mounted at once. Each agent parks its turn
    on a sentinel so the test can observe both agents busy at the same instant —
    a guaranteed overlap that a pair of fast turns would not provide (one could
    finish before the other starts, hiding a regression that serializes turns).
    Then release both and assert each chat reaches its completed message count:
    neither agent's turn blocks, drops, or overwrites the other's.
    """
    page = sculptor_instance_.page
    center = PlaywrightWorkspaceSection(page, "center")
    right = PlaywrightWorkspaceSection(page, "right")
    right_tabs = PlaywrightPanelTabElement(page, sub_section="right")

    # First agent: created with the workspace; its first exchange completes.
    start_task_and_wait_for_ready(page, prompt=_STREAM_PROMPT, workspace_name="Concurrent WS")

    # Second agent from the right section's `+` — it lands in the right section.
    right.expand_section()
    right_dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="right")
    right_dropdown.open()
    new_agent_item = right_dropdown.get_new_agent_item()
    expect(new_agent_item).to_be_visible()
    new_agent_item.click()
    expect(right_tabs.get_panel_tabs()).to_have_count(1)

    # Each section renders its own mounted chat panel; scope a chat POM to each
    # (a page-wide CHAT_PANEL locator would resolve to both).
    center_chat = PlaywrightChatPanelElement(
        locator=center.get_section().get_by_test_id(ElementIDs.CHAT_PANEL), page=page
    )
    right_chat = PlaywrightChatPanelElement(
        locator=right.get_section().get_by_test_id(ElementIDs.CHAT_PANEL), page=page
    )
    expect(right_chat).to_be_visible()
    expect(center_chat).to_be_visible()

    # Kick off a paused turn in each chat. Neither pause is released yet, so
    # once both thinking indicators are visible the two turns are provably
    # in flight at the same instant — the overlap the docstring promises.
    center_pause = FakeClaudePause()
    right_pause = FakeClaudePause()
    send_chat_message(chat_panel=right_chat, message=_paused_stream_prompt(right_pause))
    send_chat_message(chat_panel=center_chat, message=_paused_stream_prompt(center_pause))
    expect(right_chat.get_thinking_indicator()).to_be_visible()
    expect(center_chat.get_thinking_indicator()).to_be_visible()

    right_pause.release()
    center_pause.release()

    # Both turns complete independently: the center chat reaches its second
    # exchange (4 messages) and the right chat its first (2), with neither
    # stalling the other.
    wait_for_completed_message_count(chat_panel=center_chat, expected_message_count=4)
    wait_for_completed_message_count(chat_panel=right_chat, expected_message_count=2)


@user_story("to stop an agent from its own panel while another agent holds the route")
def test_stop_button_interrupts_the_panels_agent(sculptor_instance_: SculptorInstance) -> None:
    """The Stop button interrupts the PANEL's agent, not the route's agent.

    Start a first agent on a paused turn, then create a second agent — creation
    navigates the route to the new agent. Re-activating the first agent's tab
    does NOT navigate, so the route still points at the (idle) second agent
    while the panel renders the busy first one. Clicking Stop in that panel
    must interrupt the first agent; the pause is never released, so only a
    correctly targeted interrupt can end the turn — an interrupt aimed at the
    route's agent would be a no-op and leave the first agent busy.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    pause = FakeClaudePause()
    start_task_and_wait_for_ready(
        page,
        prompt=pause.prompt,
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
    # navigation.
    panel_tabs.get_panel_tab(first_panel_id).click()

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).to_be_visible()
    # The busy first agent is rendering, so the tab activation's side effects
    # have settled — and the route (the load-bearing premise) still points at
    # the second agent.
    assert task_page.get_task_id() == second_agent_id

    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()

    # The panel's agent stops. Its pause is never released, so only the Stop
    # interrupt can end the turn — a mis-targeted interrupt would leave the
    # thinking indicator visible and fail this expect.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
