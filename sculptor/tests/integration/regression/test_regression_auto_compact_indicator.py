"""Regression tests for auto-compaction detection via the stdout/stdin protocol.

Tests cover:
1. Indicator lifecycle (appears on PreCompact, dismisses on summary)
2. Fallback when no synthetic summary is emitted
3. Message ordering: the summary must stay between pre- and post-compaction
   text after the turn completes (regression for the ID-reuse bug)
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the Auto-compacting indicator appear and disappear during auto-compaction")
def test_auto_compaction_indicator_lifecycle(sculptor_instance_: SculptorInstance) -> None:
    """The Auto-compacting indicator should appear when auto-compaction starts and disappear when it finishes.

    Uses FakeClaude's ``auto_compact`` command which emits both the PreCompact
    hook_callback (shows indicator) and the ``isSynthetic`` user message
    (dismisses indicator, shows real summary text).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt="fake_claude:auto_compact",
        wait_for_agent_to_finish=False,
    )

    # The alpha pill exposes its lifecycle phase via ``data-agent-state``
    # on the pill root; the "compacting" element appears while PreCompact
    # is in flight and unmounts (or transitions) once auto-compaction
    # finishes. The POM helper returns an attribute-filtered locator that
    # only matches the compacting-state pill, so ``to_be_attached`` /
    # ``not_to_be_attached`` observe presence transitions directly — more
    # robust than polling the attribute for a transient value. We also
    # assert the visible "Compacting" label so a regression that flips the
    # text while leaving the state attribute intact still fails the test.
    chat_panel = task_page.get_chat_panel()
    compacting_pill = chat_panel.get_compacting_pill()
    expect(compacting_pill).to_be_attached()
    expect(compacting_pill).to_contain_text("Compacting")
    expect(compacting_pill).not_to_be_attached()

    context_summary = chat_panel.get_context_summary_messages()
    expect(context_summary.first).to_be_visible()


@user_story("to see the Auto-compacting indicator clear even without isSynthetic summary")
def test_auto_compaction_fallback_without_summary(sculptor_instance_: SculptorInstance) -> None:
    """The indicator should clear when normal output resumes, even if the CLI
    doesn't emit an ``isSynthetic`` user message.

    Uses FakeClaude's ``auto_compact_no_summary`` command which emits the
    PreCompact hook_callback but skips the synthetic summary, testing the
    fallback detection path.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt="fake_claude:auto_compact_no_summary",
        wait_for_agent_to_finish=False,
    )

    # See sibling test for the data-agent-state rationale.
    chat_panel = task_page.get_chat_panel()
    compacting_pill = chat_panel.get_compacting_pill()
    expect(compacting_pill).to_be_attached()
    expect(compacting_pill).to_contain_text("Compacting")
    expect(compacting_pill).not_to_be_attached()

    context_summary = chat_panel.get_context_summary_messages()
    expect(context_summary.first).to_be_visible()

    # The fallback path must not crash the agent. The post-compaction
    # ParsedAssistantResponse re-enters output_processor._process_output via
    # the streamed-turn branch; _reset_streaming_state_for_compaction nulls
    # _first_response_message_id while _streamed_turn_ids still contains the
    # message id, which trips an assertion. Wait for the turn to settle so the
    # error has time to surface, then assert no error block was emitted.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_error_block()).to_have_count(0)


@user_story("to see the compaction summary stay in place after the turn completes")
def test_auto_compaction_summary_ordering(sculptor_instance_: SculptorInstance) -> None:
    """The context summary must appear between pre- and post-compaction text,
    not jump to the end of the turn.

    Uses FakeClaude's ``auto_compact_mid_stream`` command which streams text
    before compaction, auto-compacts, then streams more text.  After the turn
    completes, the order must be:

        [user message] [pre-compact text] [context summary] [post-compact text]

    This is a regression test for a bug where the pre-compaction streaming
    message ID was reused for the post-compaction message, causing the
    frontend to deduplicate and reorder the summary to the wrong position.

    Alpha consolidates streaming text + context summary into render groups
    *inside the same `AlphaAssistantMessage`* (each text group is its own
    ``ALPHA_CHAT_TEXT`` div), so we assert DOM order via
    ``compareDocumentPosition`` between the per-text-group divs and the
    ``CONTEXT_SUMMARY`` element. This works whether the bug merges the
    pre/post into one text group or keeps them split.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt="fake_claude:auto_compact_mid_stream",
        wait_for_agent_to_finish=True,
    )

    chat_panel = task_page.get_chat_panel()

    text_blocks = chat_panel.get_text_blocks()
    pre_text = text_blocks.filter(has_text="Text before compaction.")
    post_text = text_blocks.filter(has_text="Text after compaction.")
    context_summary = chat_panel.get_context_summary_messages()

    expect(pre_text.first).to_be_visible()
    expect(post_text.first).to_be_visible()
    expect(context_summary.first).to_be_visible()

    # DOCUMENT_POSITION_FOLLOWING (bit 4) means the argument is later in DOM
    # order. DOM order is what the renderer uses to lay out the chat
    # vertically, so this captures the user-visible ordering without
    # depending on bounding-box geometry (which the virtualizer can return
    # transiently out of paint order). Re-query inside the evaluate so the
    # nodes used by ``compareDocumentPosition`` are guaranteed live in the
    # same JS frame — handles captured up front could be detached by the
    # virtualizer between capture and evaluate.
    ordering = page.evaluate(
        """({ preText, postText, summaryTestId }) => {
            const summary = document.querySelector(`[data-testid="${summaryTestId}"]`);
            if (!summary) throw new Error('CONTEXT_SUMMARY element not found');
            const findByText = (needle) => Array.from(
                document.querySelectorAll(`[data-testid="ALPHA_CHAT_TEXT"]`)
            ).find((el) => el.textContent && el.textContent.includes(needle));
            const pre = findByText(preText);
            const post = findByText(postText);
            if (!pre) throw new Error(`Pre-compaction text not found: ${preText}`);
            if (!post) throw new Error(`Post-compaction text not found: ${postText}`);
            return {
                summaryFollowsPre: !!(pre.compareDocumentPosition(summary) & 4),
                postFollowsSummary: !!(summary.compareDocumentPosition(post) & 4),
            };
        }""",
        {
            "preText": "Text before compaction.",
            "postText": "Text after compaction.",
            "summaryTestId": ElementIDs.CONTEXT_SUMMARY.value,
        },
    )

    assert ordering["summaryFollowsPre"], "Context summary must appear after the pre-compaction text in DOM order"
    assert ordering["postFollowsSummary"], "Post-compaction text must appear after the context summary in DOM order"
