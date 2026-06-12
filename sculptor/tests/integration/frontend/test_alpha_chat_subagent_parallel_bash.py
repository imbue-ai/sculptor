"""Regression test for SCU-1139: subagent tools leak into primary agent.

When the primary agent issues multiple parallel Bash tool calls AND launches
a subagent (Agent tool) in the SAME assistant message, the Agent block's
historical "isolate into its own group" behavior split the surrounding Bash
chips into multiple pill rows. The user expects the Bash chips to remain
grouped into a single pill row regardless of where the Agent appears.

The fix keeps all tools in one render group; ``ToolBlockGroup`` pulls the
Agent block out at render time and renders the ``AlphaSubagentPill`` next
to (not in between) the surrounding pill row.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _build_prompt(agent_position: str) -> str:
    """Build a ``fake_claude:interleaved_tools`` prompt with four Bash tool
    calls and a single Agent call positioned by ``agent_position`` ("middle"
    or "end"). The same primary message exercises both the buggy and
    unaffected layouts so the assertions below can stay identical.
    """
    bash_tools = [
        '{"type": "tool", "tool_name": "Bash", "tool_input": {"command": "echo 1"}}',
        '{"type": "tool", "tool_name": "Bash", "tool_input": {"command": "echo 2"}}',
        '{"type": "tool", "tool_name": "Bash", "tool_input": {"command": "echo 3"}}',
        '{"type": "tool", "tool_name": "Bash", "tool_input": {"command": "echo 4"}}',
    ]
    agent_tool = (
        '{"type": "tool", "tool_name": "Agent", "tool_input": {"prompt": "do something", "description": "subagent"}}'
    )
    if agent_position == "middle":
        ordered = bash_tools[:2] + [agent_tool] + bash_tools[2:]
    else:
        ordered = bash_tools + [agent_tool]

    blocks = ['{"type": "text", "text": "Running parallel work."}', *ordered]
    return f'fake_claude:interleaved_tools `{{"blocks": [{", ".join(blocks)}]}}`'


@pytest.mark.parametrize(
    "agent_position",
    ["middle", "end"],
    ids=["agent-in-middle-of-bash-calls", "agent-at-end-of-bash-calls"],
)
@user_story(
    "parallel Bash tool calls render as one pill row when the assistant message also launches a subagent, regardless of the Agent's position"
)
def test_bash_calls_stay_grouped_when_assistant_also_launches_subagent(
    sculptor_instance_: SculptorInstance,
    agent_position: str,
) -> None:
    """Drive the rendering pipeline with a single assistant message that
    mixes parallel Bash calls with an Agent (subagent) tool_use. The Bash
    chips must render as ONE pill row of four chips, plus one
    AlphaSubagentPill — never split into two pill rows straddling the
    subagent pill (SCU-1139).

    ``agent_position`` parametrizes the regression case (Agent in the
    middle, which split before the fix) and the unaffected sanity case
    (Agent at the end, which already grouped correctly).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_build_prompt(agent_position),
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    subagent_pills = alpha_view.get_subagent_pills()
    expect(subagent_pills).to_have_count(1)

    bash_pills = alpha_view.get_bash_blocks()
    expect(bash_pills).to_have_count(4)

    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows).to_have_count(1)
