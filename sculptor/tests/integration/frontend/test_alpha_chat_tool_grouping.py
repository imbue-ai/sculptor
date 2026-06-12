"""Integration tests for render-group shape of consecutive tool calls.

Consecutive tool_use / tool_result blocks within a single assistant message
should render as a single "N tools" group. This file contains a regression
test for the split-tools bug: when the SDK emits a
zero-delta text block between two tool_use blocks, the streaming pipeline
leaks an empty TextBlock into ``in_progress_chat_message.content`` and the
frontend render-group builder flushes the tool group on that TextBlock,
producing two 1-tool groups instead of one 2-tool group.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story(
    "to see two consecutive Greps grouped into one tool block even when the model emits a zero-delta text block between them"
)
def test_consecutive_tools_with_empty_text_between_render_as_one_group(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Regression test for the split-tools rendering bug.

    A zero-delta streaming text block between two tool_use blocks must not
    split the surrounding tools into separate render groups. The test drives
    the exact SDK event sequence:

        content_block_start(tool_use Grep, index=0)
        content_block_delta(input_json, index=0)
        content_block_stop(index=0)
        content_block_start(text, index=1)        <-- no text_delta emitted
        content_block_stop(index=1)
        content_block_start(tool_use Grep, index=2)
        content_block_delta(input_json, index=2)
        content_block_stop(index=2)

    and asserts that the rendered DOM contains exactly one
    ``ALPHA_CHAT_TOOL_GROUP`` with two ``ALPHA_CHAT_TOOL_LINE`` entries.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:interleaved_tools `{
  "blocks": [
    {"type": "tool", "tool_name": "Grep", "tool_input": {"pattern": "alpha"}},
    {"type": "text", "text": ""},
    {"type": "tool", "tool_name": "Grep", "tool_input": {"pattern": "beta"}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Both Greps should batch into a single pill row — non-diff tools are
    # rendered via ``AlphaToolPillRow`` from ``renderToolSegments`` and each
    # tool gets its own pill in that row. The bug manifests as two separate
    # pill rows (one per split render group), each showing one pill, instead
    # of one row with two pills.
    pill_rows = alpha_view.get_tool_pill_rows()
    expect(pill_rows).to_have_count(1)

    pills = alpha_view.get_tool_pills()
    expect(pills).to_have_count(2)
