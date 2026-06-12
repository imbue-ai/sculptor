"""Regression test for the auto-background-promotion tool_use/tool_result split.

When the real Claude CLI promotes a slow foreground Bash tool call (>~2.5s) to
a ``local_bash`` background task, it emits ``task_started`` + ``task_notification``
events alongside the normal ``tool_use``/``tool_result`` pair, all sharing the
same ``tool_use_id``.  The ``BackgroundTaskNotificationAgentMessage`` branch in
``sculptor/web/message_conversion.py`` flushes the in-progress chat message at
that point, sealing the ``tool_use`` into one message and forcing the
subsequent ``tool_result`` into a new one.  The alpha chat view's bash-block
segmenter (``chipRowUtils.ts`` ``segmentToolBlocks``) then renders *two*
separate bash blocks for what is conceptually a single tool call:
the first with its description (from the ``tool_use``), the second bare (from
the standalone ``tool_result``).

The ``fake_claude:auto_bg_bash`` command emits the exact JSONL sequence the
real CLI produces in this case.  A correctly behaving UI must render a single
bash block.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a single bash block when a slow foreground Bash is auto-promoted to a background task")
def test_auto_bg_bash_renders_single_block(sculptor_instance_: SculptorInstance) -> None:
    """Auto-promoted foreground Bash must render as one bash block, not two."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:auto_bg_bash `{"command": "sleep 3 && echo done", "description": "Sleep 3 seconds"}`',
    )

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_bash_blocks()).to_have_count(1)
