"""Perf scenario: switching between two agents inside the same workspace.

Same workspace, two agent panel tabs in the center section. Files and
history-tree state is shared across agents (same branch, same repo); the
things that re-fetch on switch are the chat transcript, the agent's running
state, and any agent-scoped artifact polling.

Parametrized across blend × temperature; see test_workspace_switch for the
pattern. Agents are center-section panel tabs
(``PlaywrightWorkspaceSection(page, "center")``); the active tab carries
``aria-selected``.
"""

import json
from collections.abc import Callable

import pytest
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.perf.collector import MeasurementRecorder
from sculptor.testing.playwright_utils import add_agent_and_wait_for_ready
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _fake_claude_text_prompt(text: str) -> str:
    """Build the deterministic 'fake_claude:text' command for a 1-text-block reply."""
    return f"fake_claude:text `{json.dumps({'text': text})}`"


# Number of agent turns the long-history blend builds up in agent A. Each turn
# is one user + one assistant message, so the chat ends up with
# ``2 * _LONG_HISTORY_TURNS`` messages. Adding turns scales the setup wall-time
# linearly (~0.3-0.5s/turn under Fake Claude), so this is a tunable constant.
_LONG_HISTORY_TURNS = 100


def _agent_tabs(page: Page) -> Locator:
    """The center section's agent panel tabs (``PANEL_TAB-agent:<taskId>``)."""
    return PlaywrightWorkspaceSection(page, "center").get_agent_tabs()


def _switch_to_agent(tab: Locator) -> None:
    """Click an agent tab and settle on it becoming the active tab."""
    tab.click()
    expect(tab).to_have_attribute("aria-selected", "true")
    expect(tab.page.get_by_test_id(ElementIDs.CHAT_PANEL)).to_be_visible()


# ---- Blends ---------------------------------------------------------------


def blend_default(page: Page) -> None:
    """One workspace, two agents (agent A has one turn, agent B empty)."""
    start_task_and_wait_for_ready(page, prompt="agent A first turn", workspace_name="Perf Multi Agent")
    add_agent_and_wait_for_ready(page)
    expect(_agent_tabs(page)).to_have_count(2)


def blend_long_history(page: Page) -> None:
    """One workspace, two agents. Agent A has ``_LONG_HISTORY_TURNS`` turns of
    completed chat; agent B is empty. Stresses message virtualization,
    chat-cache hydration, and the prompt-navigator dot rail on agent switch.
    """
    task_page: PlaywrightTaskPage = start_task_and_wait_for_ready(
        page, prompt=_fake_claude_text_prompt("response 1"), workspace_name="Perf Long History"
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    # Strong "agent is idle" signal between sends: empty queue + no thinking
    # indicator. We don't assert cumulative DOM counts in the loop — alpha
    # virtualizes the list so the DOM never holds all 2*N messages, and the
    # count can briefly lag the DB; the idle signal is what the next send needs.
    queue_bar = chat_panel.get_queued_message_bar()
    thinking = chat_panel.get_thinking_indicator()
    # Per-turn idle wait grows with the agent's message history, so give the
    # late loop more than the default 30s while still bounding wall time.
    per_turn_timeout_ms = 90_000
    for i in range(2, _LONG_HISTORY_TURNS + 1):
        send_chat_message(chat_panel=chat_panel, message=_fake_claude_text_prompt(f"response {i}"))
        expect(queue_bar).to_have_count(0, timeout=per_turn_timeout_ms)
        expect(thinking).not_to_be_visible(timeout=per_turn_timeout_ms)
    add_agent_and_wait_for_ready(page)
    expect(_agent_tabs(page)).to_have_count(2)


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("temperature", ["warm", "cold"])
@pytest.mark.parametrize(
    "blend",
    [
        pytest.param(blend_default, id="default"),
        pytest.param(blend_long_history, id="long_history"),
    ],
)
@user_story("perf: switching between agents in the same workspace should not over-fetch or over-render")
def test_agent_switch(
    sculptor_instance_: SculptorInstance,
    perf_recorder: MeasurementRecorder,
    blend: Callable[[Page], None],
    temperature: str,
    request: pytest.FixtureRequest,
) -> None:
    page = sculptor_instance_.page
    blend(page)

    tabs = _agent_tabs(page)
    expect(tabs).to_have_count(2)
    tab_a, tab_b = tabs.first, tabs.last

    if temperature == "warm":
        _switch_to_agent(tab_a)
        _switch_to_agent(tab_b)
    else:
        full_spa_reload(page)
        perf_recorder.assert_hook_wired()
        # The reload re-resolves the DOM; re-acquire the tab locators.
        tabs = _agent_tabs(page)
        expect(tabs).to_have_count(2)
        tab_a = tabs.first

    variant = request.node.callspec.id
    with perf_recorder.window(scenario="agent_switch", variant=variant):
        _switch_to_agent(tab_a)
