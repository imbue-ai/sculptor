import json
import time
from collections.abc import Iterable
from collections.abc import Sequence
from pathlib import Path
from queue import Queue
from threading import Event
from unittest.mock import MagicMock

import pytest

from sculptor.agents.default.claude_code_sdk.errors import ClaudeAPIError
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.default.claude_code_sdk.mcp_server import SculptorMcpServer
from sculptor.agents.default.claude_code_sdk.output_processor import ClaudeOutputProcessor
from sculptor.agents.default.claude_code_sdk.output_processor import _DEFERRED_COMPLETION_TOOLS
from sculptor.agents.default.claude_code_sdk.output_processor import _RE_TRAILING_MEDIA_TAG
from sculptor.agents.default.claude_code_sdk.process_manager_utils import parse_claude_code_json_lines
from sculptor.agents.testing.fake_claude_jsonl import make_assistant_message
from sculptor.agents.testing.fake_claude_jsonl import make_end_message
from sculptor.agents.testing.fake_claude_jsonl import make_init_message
from sculptor.agents.testing.fake_claude_jsonl import make_streaming_text_events
from sculptor.agents.testing.fake_claude_jsonl import make_streaming_tool_events
from sculptor.agents.testing.fake_claude_jsonl import make_task_notification_message
from sculptor.agents.testing.fake_claude_jsonl import make_task_started_message
from sculptor.agents.testing.fake_claude_jsonl import make_text_block
from sculptor.agents.testing.fake_claude_jsonl import make_tool_result_message
from sculptor.agents.testing.fake_claude_jsonl import make_tool_use_block
from sculptor.interfaces.agents.agent import BackgroundTaskNotificationAgentMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.interfaces.agents.errors import AgentTransientError
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import ToolUseID
from sculptor.state.chat_state import FileBlock
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.claude_state import ParsedAssistantResponse
from sculptor.state.claude_state import ParsedEndResponse
from sculptor.state.claude_state import ParsedInitResponse
from sculptor.state.claude_state import ParsedStreamEvent
from sculptor.state.claude_state import ParsedTaskNotificationResponse
from sculptor.state.claude_state import ParsedTaskStartedResponse
from sculptor.state.claude_state import ParsedTaskUpdatedResponse
from sculptor.state.messages import ChatInputUserMessage
from sculptor.web.message_conversion import convert_agent_messages_to_task_update


def _strip_trailing_tag(text: str) -> str:
    """Apply the same trailing-tag stripping logic used in _build_current_content."""
    match = _RE_TRAILING_MEDIA_TAG.search(text)
    if match:
        return text[: match.start()]
    return text


class TestTrailingMediaTagRegex:
    def test_incomplete_img_tag(self) -> None:
        assert _strip_trailing_tag("Here is a screenshot:\n<img src='/tmp/sc") == "Here is a screenshot:\n"

    def test_incomplete_video_tag(self) -> None:
        assert _strip_trailing_tag("Watch this:\n<video src='/tmp/demo.") == "Watch this:\n"

    def test_just_opening_bracket_and_tag(self) -> None:
        assert _strip_trailing_tag("Hello <img") == "Hello "

    def test_img_with_partial_attributes(self) -> None:
        text = "Results:\n<img src='/path/to/image.png' alt='test"
        assert _strip_trailing_tag(text) == "Results:\n"

    def test_complete_tag_not_stripped(self) -> None:
        """A complete tag (with closing >) should NOT be matched by the trailing regex."""
        text = "Here: <img src='/tmp/test.png' alt='test'>"
        assert _strip_trailing_tag(text) == text

    def test_no_tag_at_all(self) -> None:
        text = "Just some plain text with no tags."
        assert _strip_trailing_tag(text) == text

    def test_complete_tag_followed_by_text(self) -> None:
        text = "<img src='/tmp/a.png'> and more text"
        assert _strip_trailing_tag(text) == text

    def test_case_insensitive(self) -> None:
        assert _strip_trailing_tag("Hello <IMG src='/tmp/x") == "Hello "
        assert _strip_trailing_tag("Hello <Video src='/tmp/x") == "Hello "

    def test_preserves_text_before_incomplete_tag(self) -> None:
        text = "Line 1\nLine 2\nLine 3\n<img src='/very/long/path/to/screenshot"
        assert _strip_trailing_tag(text) == "Line 1\nLine 2\nLine 3\n"

    def test_does_not_match_non_media_tags(self) -> None:
        """Tags like <div>, <span> should not be stripped."""
        text = "Hello <div class='foo"
        assert _strip_trailing_tag(text) == text

    def test_multiple_complete_tags_then_incomplete(self) -> None:
        """Only the trailing incomplete tag is stripped."""
        text = "<img src='/a.png'> text <img src='/b"
        assert _strip_trailing_tag(text) == "<img src='/a.png'> text "

    def test_regex_pattern_matches_expected(self) -> None:
        """Verify the regex matches the specific patterns we expect."""
        assert _RE_TRAILING_MEDIA_TAG.search("<img") is not None
        assert _RE_TRAILING_MEDIA_TAG.search("<video") is not None
        assert _RE_TRAILING_MEDIA_TAG.search("<img src='x'>") is None
        assert _RE_TRAILING_MEDIA_TAG.search("<div") is None


def _make_processor_for_persistence_test(
    completed_streaming_blocks: list,  # noqa: ANN001
    extracted_file_blocks: dict,  # noqa: ANN001
) -> ClaudeOutputProcessor:
    """Create a minimal ClaudeOutputProcessor for testing _build_streamed_persistence_content.

    Accepts ``completed_streaming_blocks`` as a positional list for test
    readability; the processor's internal representation is a sparse
    dict[int, block] keyed by streaming index, so the list is converted here.

    ``extracted_file_blocks`` is the processor's real representation: a
    dict mapping a source text block's streaming index to the media (and
    interleaved text) extracted from it. The media is spliced back in right
    after the block at that index.
    """
    processor = object.__new__(ClaudeOutputProcessor)
    processor._completed_streaming_blocks = dict(enumerate(completed_streaming_blocks))
    processor._text_accumulators = {}
    processor._extracted_file_blocks = extracted_file_blocks
    return processor


class TestBuildStreamedPersistenceContent:
    """Tests for _build_streamed_persistence_content which builds persistence content from streaming state."""

    def test_text_and_file_and_tool(self) -> None:
        """The typical bug scenario: text with img tag followed by tool call."""
        tool_block = ToolUseBlock(id=ToolUseID("tool_1"), name="Read", input={"file_path": "/tmp/x"})
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[
                TextBlock(text=""),  # empty placeholder at index 0
                TextBlock(text="Here is a screenshot"),  # cleaned text at index 1
                tool_block,  # at index 2 (overwrote the FileBlock)
            ],
            # The screenshot was extracted from the text block at index 1.
            extracted_file_blocks={1: [FileBlock(source="/tmp/screenshot.png")]},
        )
        result = processor._build_streamed_persistence_content()
        assert result == (
            TextBlock(text="Here is a screenshot"),
            FileBlock(source="/tmp/screenshot.png"),
            tool_block,
        )

    def test_empty_text_blocks_are_skipped(self) -> None:
        """TextBlocks with only whitespace are filtered out."""
        tool_block = ToolUseBlock(id=ToolUseID("tool_1"), name="Bash", input={})
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[TextBlock(text=""), TextBlock(text="  \n  "), tool_block],
            extracted_file_blocks={},
        )
        result = processor._build_streamed_persistence_content()
        assert result == (tool_block,)

    def test_tool_only(self) -> None:
        """When streaming only had a ToolUseBlock (no text), return just the tool."""
        tool_block = ToolUseBlock(id=ToolUseID("tool_1"), name="Bash", input={})
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[tool_block],
            extracted_file_blocks={},
        )
        result = processor._build_streamed_persistence_content()
        assert result == (tool_block,)

    def test_text_only_no_tools(self) -> None:
        """When streaming had text but no tools, FileBlocks go at the end."""
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[TextBlock(text="Hello world")],
            extracted_file_blocks={0: [FileBlock(source="/tmp/img.png")]},
        )
        result = processor._build_streamed_persistence_content()
        assert result == (
            TextBlock(text="Hello world"),
            FileBlock(source="/tmp/img.png"),
        )

    def test_multiple_file_blocks(self) -> None:
        """Multiple FileBlocks are all inserted before ToolUseBlocks."""
        tool_block = ToolUseBlock(id=ToolUseID("tool_1"), name="Bash", input={})
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[TextBlock(text="Two images:"), tool_block],
            # Both images were extracted from the text block at index 0.
            extracted_file_blocks={
                0: [
                    FileBlock(source="/tmp/img1.png"),
                    FileBlock(source="/tmp/img2.png"),
                ]
            },
        )
        result = processor._build_streamed_persistence_content()
        assert result == (
            TextBlock(text="Two images:"),
            FileBlock(source="/tmp/img1.png"),
            FileBlock(source="/tmp/img2.png"),
            tool_block,
        )

    def test_image_after_tool_keeps_order(self) -> None:
        """An <img> in text that comes AFTER a tool call stays after the tool.

        Regression for the streaming reorder bug: extracted media used to be spliced
        before the FIRST ToolUseBlock, so an image whose source text came after a tool
        jumped in front of it (and earlier-streamed blocks visibly moved). Keying the
        extracted blocks by their source streaming index keeps them in place.
        """
        tool_block = ToolUseBlock(id=ToolUseID("tool_1"), name="Bash", input={"command": "echo hi"})
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[
                tool_block,  # index 0
                TextBlock(text="look "),  # index 1: text the image was extracted from
            ],
            # The image (and its trailing text) were extracted from index 1, AFTER the tool.
            extracted_file_blocks={1: [FileBlock(source="/tmp/shot.png"), TextBlock(text=" done")]},
        )
        result = processor._build_streamed_persistence_content()
        assert result == (
            tool_block,
            TextBlock(text="look "),
            FileBlock(source="/tmp/shot.png"),
            TextBlock(text=" done"),
        )

    def test_empty_streaming_state(self) -> None:
        """When nothing was streamed, return empty tuple."""
        processor = _make_processor_for_persistence_test(
            completed_streaming_blocks=[],
            extracted_file_blocks={},
        )
        result = processor._build_streamed_persistence_content()
        assert result == ()


def _drain_queue(q: Queue) -> list:
    """Drain all messages from a Queue into a list."""
    messages = []
    while not q.empty():
        messages.append(q.get_nowait())
    return messages


def _make_processor_for_jsonl_test() -> ClaudeOutputProcessor:
    """Create a ClaudeOutputProcessor suitable for feeding JSONL events.

    Uses a mocked RunningProcess (only get_queue is called by the constructor)
    so that the real __init__ runs and all state is properly initialized.
    """
    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()

    # The output processor touches the environment's state path when sending
    # context-usage requests. Make read_file raise FileNotFoundError and give
    # get_state_path a real Path so any incidental state access is harmless.
    mock_env = MagicMock()
    mock_env.read_file.side_effect = FileNotFoundError
    mock_env.get_state_path.return_value = Path("/tmp/sculptor_test_state")

    return ClaudeOutputProcessor(
        process=mock_process,
        source_command="test",
        output_message_queue=Queue(),
        environment=mock_env,
        diff_tracker=None,
        task_id=TaskID(),
        session_id_written_event=Event(),
        harness=CLAUDE_CODE_HARNESS,
        streaming_enabled=True,
    )


def _make_task_updated_message(task_id: str, status: str = "completed") -> dict:
    """Return a dict for a system/task_updated message (CLI-shaped)."""
    return {
        "type": "system",
        "subtype": "task_updated",
        "task_id": task_id,
        "patch": {"status": status},
    }


def _make_minimal_end_message(session_id: str = "s1") -> dict:
    """Minimal end-of-turn message used by the state-machine tests.

    total_cost_usd is None because these tests only exercise the turn
    cleanup state machine and do not need a cost value.
    """
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "",
        "session_id": session_id,
        "duration_ms": 0,
        "duration_api_ms": 0,
        "num_turns": 0,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "total_cost_usd": None,
    }


def _feed_jsonl(processor: ClaudeOutputProcessor, jsonl_dicts: list[dict]) -> None:
    """Parse JSONL dicts and dispatch them through the processor.

    Mirrors the dispatch logic in _process_output without requiring a real process.
    """
    for d in jsonl_dicts:
        line = json.dumps(d)
        result = parse_claude_code_json_lines(line, processor.tool_use_map, processor.diff_tracker)
        if result is None:
            continue
        if isinstance(result, ParsedStreamEvent):
            processor._handle_stream_event(result)
        elif isinstance(result, ParsedInitResponse):
            processor._parse_init_response(result)
        elif isinstance(result, ParsedAssistantResponse):
            processor._parse_assistant_response(result)
        elif isinstance(result, ParsedTaskStartedResponse):
            processor._pending_background_tasks.add(result.task_id)
            tool_use_info = processor.tool_use_map.get(result.tool_use_id)
            if tool_use_info is not None:
                processor._task_id_to_tool_name[result.task_id] = tool_use_info[0]
        elif isinstance(result, ParsedTaskUpdatedResponse):
            if result.status in ("completed", "failed", "stopped"):
                tool_name = processor._task_id_to_tool_name.get(result.task_id, "")
                if tool_name in _DEFERRED_COMPLETION_TOOLS:
                    processor._completed_pending_deferred.add(result.task_id)
                    if processor._completed_pending_deferred_deadline is None:
                        processor._completed_pending_deferred_deadline = time.monotonic() + 5.0
                else:
                    processor._completed_via_task_updated.add(result.task_id)
        elif isinstance(result, ParsedTaskNotificationResponse):
            processor._pending_background_tasks.discard(result.task_id)
            processor._completed_pending_deferred.discard(result.task_id)
            if not processor._completed_pending_deferred:
                processor._completed_pending_deferred_deadline = None
            processor.found_final_message = False
            processor.output_message_queue.put(
                BackgroundTaskNotificationAgentMessage(
                    message_id=AgentMessageID(),
                    background_task_id=result.task_id,
                    tool_use_id=result.tool_use_id,
                    status=result.status,
                    summary=result.summary,
                )
            )
        elif isinstance(result, ParsedEndResponse):
            processor._parse_stream_end_response(result)


class TestNotificationDuringStreaming:
    """Regression tests for SCU-267: ParsedTaskNotificationResponse arriving mid-stream.

    Tests use JSONL input sequences (via fake_claude_jsonl builders) fed through
    parse_claude_code_json_lines, mirroring the real data flow instead of
    hardcoding internal processor state.
    """

    def test_notification_mid_stream_preserves_streaming_state(self) -> None:
        """A notification arriving mid-stream must not disturb streaming.

        Input:  system/init → partial streaming text → notification
        Expect: queue contains partials with a consistent message ID,
                plus one BackgroundTaskNotificationAgentMessage.
                Calling _emit_partial_message after the notification must not crash.
        """
        processor = _make_processor_for_jsonl_test()

        # Build the JSONL sequence: init, partial stream, then notification mid-stream.
        init = make_init_message(session_id="session_001")
        stream_events = make_streaming_text_events(message_id="msg_001", text="Hello world")
        notification = make_task_notification_message(
            task_id="bg_task_001", tool_use_id="toolu_bg_001", status="completed"
        )
        # Feed init + first 3 stream events (message_start, content_block_start, delta)
        # to leave the processor mid-stream, then the notification.
        _feed_jsonl(processor, [init] + stream_events[:3] + [notification])

        # _emit_partial_message must not crash (the bug was AssertionError here).
        processor._emit_partial_message()

        messages = _drain_queue(processor.output_message_queue)
        notifications = [m for m in messages if isinstance(m, BackgroundTaskNotificationAgentMessage)]
        partials = [m for m in messages if isinstance(m, PartialResponseBlockAgentMessage)]

        assert len(notifications) == 1
        assert len(partials) >= 2  # at least one from streaming + one from explicit call
        # All partials must share the same message ID (notification didn't reset it).
        partial_ids = {p.first_response_message_id for p in partials}
        assert len(partial_ids) == 1

    def test_init_after_notification_resets_for_new_cycle(self) -> None:
        """system/init after a notification starts a fresh request cycle.

        Input:  init_1 → full stream → notification → init_2 → stream_2 (message_start only)
        Expect: the second stream's partials have a different message ID than the first.
        """
        processor = _make_processor_for_jsonl_test()

        # Build the full JSONL sequence.
        init_1 = make_init_message(session_id="session_001")
        stream_1 = make_streaming_text_events(message_id="msg_001", text="Hello")
        notification = make_task_notification_message(
            task_id="bg_task_001", tool_use_id="toolu_bg_001", status="completed"
        )
        init_2 = make_init_message(session_id="session_002")
        stream_2 = make_streaming_text_events(message_id="bg_msg_001", text="Background done")

        _feed_jsonl(processor, [init_1] + stream_1 + [notification, init_2] + stream_2[:3])

        # Emit a partial for the second stream so we can inspect its ID.
        processor._emit_partial_message()

        messages = _drain_queue(processor.output_message_queue)
        partials = [m for m in messages if isinstance(m, PartialResponseBlockAgentMessage)]

        # Partials from stream_1 and stream_2 must have different message IDs.
        unique_ids = {p.first_response_message_id for p in partials}
        assert len(unique_ids) == 2


class TestDeferredCompletionCleanup:
    """Tests for deferred cleanup of task_updated{completed} for Monitor.

    Bash run_in_background's task_updated{completed} signals the task is done;
    cleanup must fire at the current turn's result/success.

    Monitor's task_updated{completed} signals the underlying bash exited, but
    the CLI emits a follow-up event-delivery turn (init→assistant→result)
    AFTER the current turn's result/success. Cleanup must defer one turn so
    the agent gets to react in that follow-up turn.
    """

    def _arm_monitor_and_close_turn(self, processor: ClaudeOutputProcessor, task_id: str = "task_monitor_1") -> None:
        """Feed turn 1 events: init, assistant calls Monitor, task_started, result."""
        tool_use_id = "toolu_monitor_1"
        _feed_jsonl(
            processor,
            [
                make_init_message(session_id="s1"),
                make_assistant_message(
                    message_id="msg_1",
                    content_blocks=[
                        make_tool_use_block(
                            tool_id=tool_use_id,
                            tool_name="Monitor",
                            tool_input={"command": "echo X", "timeout_ms": 60000},
                        )
                    ],
                ),
                make_task_started_message(
                    task_id=task_id,
                    tool_use_id=tool_use_id,
                    description="watcher",
                    task_type="local_bash",
                ),
            ],
        )

    def test_monitor_task_updated_defers_cleanup(self) -> None:
        """task_updated{Monitor, completed} must NOT clear at current turn's result/success.

        Without the defer, the loop exits after turn 1 → process killed before
        the CLI's follow-up event-delivery turn → agent never reacts to the event.
        """
        processor = _make_processor_for_jsonl_test()
        self._arm_monitor_and_close_turn(processor)

        # Mid-turn: Monitor's bash exits cleanly.
        _feed_jsonl(processor, [_make_task_updated_message(task_id="task_monitor_1", status="completed")])

        # End the current turn.
        _feed_jsonl(processor, [_make_minimal_end_message(session_id="s1")])

        # The Monitor task must still be pending — cleanup is deferred to the
        # follow-up turn. If this fails, the loop would exit before the CLI's
        # event-delivery turn.
        assert "task_monitor_1" in processor._pending_background_tasks
        assert "task_monitor_1" in processor._completed_pending_deferred
        assert "task_monitor_1" not in processor._completed_via_task_updated
        # Loop keep-alive condition must be true so the loop continues.
        keep_alive = (
            (not processor.found_final_message)
            or bool(processor._pending_background_tasks)
            or processor._pending_wakeup
        )
        assert keep_alive

    def test_followup_init_promotes_and_next_result_clears(self) -> None:
        """init for the follow-up turn promotes the deferred entry; next result clears it."""
        processor = _make_processor_for_jsonl_test()
        self._arm_monitor_and_close_turn(processor)
        _feed_jsonl(processor, [_make_task_updated_message(task_id="task_monitor_1", status="completed")])
        _feed_jsonl(processor, [_make_minimal_end_message(session_id="s1")])

        # CLI starts the follow-up event-delivery turn.
        _feed_jsonl(processor, [make_init_message(session_id="s1")])

        # Promotion happens at init: deferred cleared, completion now ready
        # for the new turn's result/success.
        assert processor._completed_pending_deferred == set()
        assert processor._completed_pending_deferred_deadline is None
        assert "task_monitor_1" in processor._completed_via_task_updated
        # Task is still pending — won't clear until this new turn's result.
        assert "task_monitor_1" in processor._pending_background_tasks

        # End the follow-up turn → cleanup runs → loop will exit.
        _feed_jsonl(processor, [_make_minimal_end_message(session_id="s1")])

        assert "task_monitor_1" not in processor._pending_background_tasks
        keep_alive = (
            (not processor.found_final_message)
            or bool(processor._pending_background_tasks)
            or processor._pending_wakeup
        )
        assert not keep_alive

    def test_bash_run_in_background_clears_immediately(self) -> None:
        """Bash run_in_background's task_updated{completed} must clear at current
        turn's result/success — its task_notification was dropped by the CLI
        (Scenario 2), so we have no other signal that the task is done.
        """
        processor = _make_processor_for_jsonl_test()
        # Turn 1: agent calls Bash with run_in_background=true.
        _feed_jsonl(
            processor,
            [
                make_init_message(session_id="s1"),
                make_assistant_message(
                    message_id="msg_1",
                    content_blocks=[
                        make_tool_use_block(
                            tool_id="toolu_bash_1",
                            tool_name="Bash",
                            tool_input={"command": "sleep 3", "run_in_background": True},
                        )
                    ],
                ),
                make_task_started_message(
                    task_id="task_bash_1",
                    tool_use_id="toolu_bash_1",
                    description="bg sleep",
                    task_type="local_bash",
                ),
                _make_task_updated_message(task_id="task_bash_1", status="completed"),
                _make_minimal_end_message(session_id="s1"),
            ],
        )

        # Bash bg cleared immediately — there's no follow-up turn coming.
        assert "task_bash_1" not in processor._pending_background_tasks
        assert "task_bash_1" not in processor._completed_pending_deferred
        keep_alive = (
            (not processor.found_final_message)
            or bool(processor._pending_background_tasks)
            or processor._pending_wakeup
        )
        assert not keep_alive

    def test_task_notification_supersedes_deferred(self) -> None:
        """If Monitor's task_notification eventually arrives, drop the deferred
        entry so it doesn't replay as a stale completion later.
        """
        processor = _make_processor_for_jsonl_test()
        self._arm_monitor_and_close_turn(processor)
        _feed_jsonl(processor, [_make_task_updated_message(task_id="task_monitor_1", status="completed")])

        assert "task_monitor_1" in processor._completed_pending_deferred

        # task_notification arrives — supersedes the deferred path.
        _feed_jsonl(
            processor,
            [
                make_task_notification_message(
                    task_id="task_monitor_1",
                    tool_use_id="toolu_monitor_1",
                    status="completed",
                )
            ],
        )

        assert processor._completed_pending_deferred == set()
        assert processor._completed_pending_deferred_deadline is None
        assert "task_monitor_1" not in processor._pending_background_tasks


def _make_processor_for_idle_timeout_test(
    interrupted_event: Event | None = None,
) -> tuple[ClaudeOutputProcessor, MagicMock]:
    """Create a ClaudeOutputProcessor for testing idle timeout behavior.

    Returns the processor and the mock process (for setting side_effect/return_value).
    """
    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()
    mock_process.is_finished.return_value = False

    processor = ClaudeOutputProcessor(
        process=mock_process,
        source_command="test",
        output_message_queue=Queue(),
        environment=MagicMock(),
        diff_tracker=None,
        task_id=TaskID(),
        session_id_written_event=Event(),
        harness=CLAUDE_CODE_HARNESS,
        streaming_enabled=True,
        interrupted_event=interrupted_event,
    )
    return processor, mock_process


class TestIdleTimeout:
    """Tests for the idle timeout in _process_output.

    The idle timeout should only fire after an interrupt has been sent,
    not during normal operation where tool execution can take arbitrarily long.
    """

    def test_no_timeout_without_interrupt(self) -> None:
        """Normal operation: no timeout even if idle time exceeds threshold."""
        processor, mock_process = _make_processor_for_idle_timeout_test(interrupted_event=Event())
        # Set idle timeout very low so we can test quickly
        processor._idle_timeout_seconds = 0.05
        # Backdate _last_output_time so idle time exceeds threshold
        processor._last_output_time = time.monotonic() - 1.0

        # After one empty queue poll, the loop should NOT break (no interrupt set).
        # Make process finish after one iteration so the loop exits naturally.
        call_count = 0

        def is_finished_side_effect() -> bool:
            nonlocal call_count
            call_count += 1
            # Let the loop run once (idle check), then exit on the next iteration
            return call_count > 1

        mock_process.is_finished.side_effect = is_finished_side_effect

        processor._process_output()

        # The loop exited because is_finished returned True, not because of idle timeout.
        # If idle timeout had fired, found_final_message would still be False AND
        # the warning log would have been emitted. Verify the loop ran at least once.
        assert call_count > 1
        assert not processor.found_final_message

    def test_timeout_fires_after_interrupt(self) -> None:
        """After interrupt: idle timeout should break the loop."""
        interrupted = Event()
        interrupted.set()  # Simulate interrupt already sent
        processor, mock_process = _make_processor_for_idle_timeout_test(interrupted_event=interrupted)
        processor._idle_timeout_seconds = 0.05
        processor._last_output_time = time.monotonic() - 1.0

        # The loop should break due to idle timeout (not process exit)
        processor._process_output()

        # The loop exited because of idle timeout — process was never finished
        assert not processor.found_final_message
        mock_process.is_finished.return_value = False

    def test_no_timeout_with_no_interrupted_event(self) -> None:
        """When interrupted_event is None (not passed), no timeout fires."""
        processor, mock_process = _make_processor_for_idle_timeout_test(interrupted_event=None)
        processor._idle_timeout_seconds = 0.05
        processor._last_output_time = time.monotonic() - 1.0

        call_count = 0

        def is_finished_side_effect() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > 1

        mock_process.is_finished.side_effect = is_finished_side_effect

        processor._process_output()

        assert call_count > 1
        assert not processor.found_final_message


def _make_processor_for_interrupt_test(
    interrupted_event: Event | None = None,
) -> ClaudeOutputProcessor:
    """Create a ClaudeOutputProcessor for testing interrupt error suppression.

    Unlike _make_processor_for_idle_timeout_test, this configures the environment
    mock with a real claude jsonl path so _parse_stream_end_response does not
    crash on MagicMock path objects.
    """
    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()
    mock_process.is_finished.return_value = False
    mock_process.returncode = None

    mock_env = MagicMock()
    mock_env.get_user_home_directory.return_value = Path("/nonexistent")
    mock_env.get_working_directory.return_value = Path("/nonexistent/code")

    return ClaudeOutputProcessor(
        process=mock_process,
        source_command="test",
        output_message_queue=Queue(),
        environment=mock_env,
        diff_tracker=None,
        task_id=TaskID(),
        session_id_written_event=Event(),
        harness=CLAUDE_CODE_HARNESS,
        streaming_enabled=True,
        interrupted_event=interrupted_event,
    )


class TestInterruptedErrorSuppression:
    """Tests that error end responses are suppressed when the agent was interrupted.

    When the user interrupts an agent turn mid-command, Claude Code emits a
    ParsedEndResponse with is_error=True and empty result. If the interrupted
    event is set, _parse_stream_end_response should NOT raise AgentClientError
    — the process manager handles interrupts separately.
    """

    def test_error_end_response_does_not_raise_when_interrupted(self) -> None:
        """An error end response should be silently ignored when interrupted."""
        interrupted = Event()
        interrupted.set()
        processor = _make_processor_for_interrupt_test(interrupted_event=interrupted)

        init = make_init_message(session_id="session_001")
        end = make_end_message(session_id=None, is_error=True, result="")

        # Should NOT raise AgentClientError
        _feed_jsonl(processor, [init, end])

        assert processor.found_final_message

    def test_error_end_response_raises_when_not_interrupted(self) -> None:
        """Without interrupt, an error end response should raise AgentClientError as usual."""
        processor = _make_processor_for_interrupt_test(interrupted_event=Event())

        init = make_init_message(session_id="session_001")
        end = make_end_message(session_id=None, is_error=True, result="")

        with pytest.raises(AgentClientError):
            _feed_jsonl(processor, [init, end])

    def test_error_end_response_raises_when_no_interrupted_event(self) -> None:
        """When no interrupted_event was provided, errors should still raise."""
        processor = _make_processor_for_interrupt_test(interrupted_event=None)

        init = make_init_message(session_id="session_001")
        end = make_end_message(session_id=None, is_error=True, result="")

        with pytest.raises(AgentClientError):
            _feed_jsonl(processor, [init, end])


class TestApiErrorClassification:
    """Transient-vs-permanent classification of error end responses.

    These feed real JSONL frames through the parser and processor dispatch loop
    (via _feed_jsonl), so they exercise both the api_error_status parse site and
    _parse_stream_end_response's classification end-to-end. The exception type is
    the only observable that reflects the classification — at the UI layer every
    recoverable AgentClientError renders identically, so this is the level that
    can distinguish them.
    """

    def test_structured_transient_status_raises_transient_error(self) -> None:
        """A structured api_error_status in TRANSIENT_ERROR_CODES (429) is transient."""
        processor = _make_processor_for_interrupt_test(interrupted_event=Event())
        init = make_init_message(session_id="session_001")
        # Reworded text that does NOT start with "API Error", proving the structured
        # field drives classification rather than the string-prefix fallback.
        end = make_end_message(session_id=None, is_error=True, result="Overloaded", api_error_status=429)

        with pytest.raises(AgentTransientError):
            _feed_jsonl(processor, [init, end])

    def test_structured_permanent_status_raises_claude_api_error(self) -> None:
        """A structured api_error_status outside TRANSIENT_ERROR_CODES (400) is permanent."""
        processor = _make_processor_for_interrupt_test(interrupted_event=Event())
        init = make_init_message(session_id="session_001")
        end = make_end_message(session_id=None, is_error=True, result="Bad request", api_error_status=400)

        with pytest.raises(ClaudeAPIError) as exc_info:
            _feed_jsonl(processor, [init, end])
        # A permanent API error must not be mistaken for a retryable transient one.
        assert not isinstance(exc_info.value, AgentTransientError)

    def test_string_prefix_fallback_still_classifies_transient(self) -> None:
        """Without the structured field, "API Error: 429 ..." text still maps to transient."""
        processor = _make_processor_for_interrupt_test(interrupted_event=Event())
        init = make_init_message(session_id="session_001")
        end = make_end_message(session_id=None, is_error=True, result="API Error: 429 Rate limited")

        with pytest.raises(AgentTransientError):
            _feed_jsonl(processor, [init, end])

    def test_plain_error_text_raises_generic_client_error(self) -> None:
        """A non-API error with neither the field nor the prefix stays a plain client error."""
        processor = _make_processor_for_interrupt_test(interrupted_event=Event())
        init = make_init_message(session_id="session_001")
        end = make_end_message(session_id=None, is_error=True, result="Something else went wrong")

        with pytest.raises(AgentClientError) as exc_info:
            _feed_jsonl(processor, [init, end])
        # Neither transient nor a Claude API error — the base client error, not a subclass.
        assert type(exc_info.value) is AgentClientError


def _make_processor_with_mcp_server(
    mcp_server: SculptorMcpServer | None,
) -> ClaudeOutputProcessor:
    mock_process = MagicMock()
    mock_process.get_queue.return_value = Queue()
    return ClaudeOutputProcessor(
        process=mock_process,
        source_command="test",
        output_message_queue=Queue(),
        environment=MagicMock(),
        diff_tracker=None,
        task_id=TaskID(),
        session_id_written_event=Event(),
        harness=CLAUDE_CODE_HARNESS,
        streaming_enabled=True,
        mcp_server=mcp_server,
    )


class TestMcpMessageDispatch:
    """Tests for the new ``mcp_message`` branch in ``_maybe_handle_control_request``."""

    def test_mcp_message_for_sculptor_server_routes_to_handle_message(self) -> None:
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)

        line = json.dumps(
            {
                "type": "control_request",
                "request_id": "req_42",
                "request": {
                    "subtype": "mcp_message",
                    "server_name": "sculptor",
                    "message": {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
                },
            }
        )
        assert processor._maybe_handle_control_request(line) is True
        mcp_server.handle_message.assert_called_once_with(
            "req_42",
            {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
        )

    def test_mcp_message_for_unknown_server_responds_with_error(self) -> None:
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)
        processor._respond_to_control_request = MagicMock()

        line = json.dumps(
            {
                "type": "control_request",
                "request_id": "req_99",
                "request": {
                    "subtype": "mcp_message",
                    "server_name": "some-other-server",
                    "message": {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
                },
            }
        )
        assert processor._maybe_handle_control_request(line) is True
        mcp_server.handle_message.assert_not_called()
        processor._respond_to_control_request.assert_called_once_with(
            "req_99",
            {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "error": {"code": -32600, "message": "Unknown MCP server"},
                }
            },
        )


class TestSculptorMcpToolDetection:
    """Tests that the AUQ / ExitPlanMode handlers fire on the MCP FQN names
    and not on the now-suppressed built-in names."""

    def _make_tool_block(self, name: str, tool_input: dict) -> ToolUseBlock:
        return ToolUseBlock(id=ToolUseID(f"toolu_{name}"), name=name, input=tool_input)

    def test_ask_user_question_handler_fires_on_mcp_fqn(self) -> None:
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)
        block = self._make_tool_block(
            "mcp__sculptor__ask_user_question",
            {"questions": [{"question": "Q?", "header": "Header", "options": [], "multi_select": False}]},
        )
        assert processor._maybe_handle_ask_user_question(block) is True
        mcp_server.register_tool_use_id.assert_called_once_with(block.id, "mcp__sculptor__ask_user_question")

    def test_ask_user_question_handler_does_not_fire_on_builtin_name(self) -> None:
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)
        block = self._make_tool_block(
            "AskUserQuestion",
            {"questions": [{"question": "Q?", "header": "Header", "options": [], "multi_select": False}]},
        )
        assert processor._maybe_handle_ask_user_question(block) is False
        mcp_server.register_tool_use_id.assert_not_called()

    def test_exit_plan_mode_handler_fires_on_mcp_fqn(self) -> None:
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)
        block = self._make_tool_block("mcp__sculptor__exit_plan_mode", {"plan": "..."})
        assert processor._maybe_handle_exit_plan_mode(block) is True
        mcp_server.register_tool_use_id.assert_called_once_with(block.id, "mcp__sculptor__exit_plan_mode")

    def test_exit_plan_mode_handler_does_not_fire_on_builtin_name(self) -> None:
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)
        block = self._make_tool_block("ExitPlanMode", {"plan": "..."})
        assert processor._maybe_handle_exit_plan_mode(block) is False
        mcp_server.register_tool_use_id.assert_not_called()

    def test_ask_user_question_handler_silently_skips_panel_on_invalid_input(self, explode_on_error: object) -> None:
        """When the agent emits a ``mcp__sculptor__ask_user_question`` tool_use
        whose input fails Pydantic validation, the handler must NOT emit a
        chat-visible ``WarningAgentMessage`` — the MCP server independently
        responds to the matching ``tools/call`` with a JSON-RPC error so the
        agent can retry. Surfacing a warning here would just be redundant
        noise on top of the agent's retry.

        The autouse ``explode_on_error`` fixture (see ``sculptor/conftest.py``)
        enforces that no ``logger.error`` is emitted from this path.
        """
        mcp_server = MagicMock()
        processor = _make_processor_with_mcp_server(mcp_server)
        queue: Queue = Queue()
        processor.output_message_queue = queue

        block = self._make_tool_block(
            "mcp__sculptor__ask_user_question",
            {"questions": [{"question": "Q?", "header": "H", "options": [{}], "multi_select": False}]},
        )

        assert processor._maybe_handle_ask_user_question(block) is False

        emitted = []
        while not queue.empty():
            emitted.append(queue.get_nowait())
        assert emitted == [], f"expected no chat messages, got {emitted!r}"
        mcp_server.register_tool_use_id.assert_not_called()


def _make_interleaved_stream_events(message_id: str, blocks: Sequence[dict]) -> list[dict]:
    """Build a streaming event sequence for an assistant message with arbitrary
    ordered text and tool_use content blocks.

    Unlike ``make_streaming_tool_events``, this helper lets the caller place a
    text block at *any* index — including between two tool_use blocks — and
    lets the caller emit zero-delta text blocks by passing ``{"type": "text",
    "text": ""}``. Both are shapes the real SDK emits but existing helpers do
    not produce.

    Each block dict must be one of:
        - ``{"type": "text", "text": <str>}`` (no delta emitted when text is "")
        - ``{"type": "tool_use", "id": <str>, "name": <str>, "input": <dict>}``
    """
    events: list[dict] = [
        {
            "type": "stream_event",
            "event": {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": "fake-claude",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
            "parent_tool_use_id": None,
        }
    ]

    for index, block in enumerate(blocks):
        if block["type"] == "text":
            events.append(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {"type": "text", "text": ""},
                    },
                }
            )
            if block["text"]:
                events.append(
                    {
                        "type": "stream_event",
                        "event": {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": block["text"]},
                        },
                    }
                )
            events.append(
                {
                    "type": "stream_event",
                    "event": {"type": "content_block_stop", "index": index},
                }
            )
        elif block["type"] == "tool_use":
            events.append(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": block["id"],
                            "name": block["name"],
                            "input": {},
                        },
                    },
                }
            )
            events.append(
                {
                    "type": "stream_event",
                    "event": {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": json.dumps(block["input"]),
                        },
                    },
                }
            )
            events.append(
                {
                    "type": "stream_event",
                    "event": {"type": "content_block_stop", "index": index},
                }
            )
        else:
            raise ValueError(f"Unsupported block type: {block['type']!r}")

    return events


class TestPartialAndPersistenceShapeEquality:
    """Shape-equality invariants between ``_build_current_content`` and
    ``_build_streamed_persistence_content``.

    After every streaming content block has been finalized (no accumulators
    in flight), the two functions should return the same content. Any
    divergence means empty or sentinel ``TextBlock``s used for positional
    indexing are leaking into partial messages (which the frontend renders)
    while being filtered from the persistence message (which the frontend
    cannot use to correct the already-built in-progress chat message once
    ``streaming.message_was_streamed`` is set).

    Each test drives a realistic sequence of SDK stream events through the
    processor, then asserts the invariant.
    """

    def _feed_and_get_both_shapes(self, blocks: Sequence[dict]) -> tuple[list, tuple]:
        processor = _make_processor_for_jsonl_test()
        events = [make_init_message(session_id="sess_1")] + _make_interleaved_stream_events(
            message_id="msg_1", blocks=blocks
        )
        _feed_jsonl(processor, events)
        return (
            processor._materialize_content(include_in_progress=True),
            processor._build_streamed_persistence_content(),
        )

    def test_non_empty_text_between_tools_produces_equal_shapes(self) -> None:
        """Baseline: when text between two tools is non-empty, partial and
        persistence agree. This should pass today."""
        current, persistence = self._feed_and_get_both_shapes(
            [
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.ts"}},
                {"type": "text", "text": "Now checking the second file."},
                {"type": "tool_use", "id": "toolu_2", "name": "Read", "input": {"file_path": "b.ts"}},
            ]
        )
        assert tuple(current) == persistence

    def test_zero_delta_text_between_tools_produces_equal_shapes(self) -> None:
        """Reproduces the split-tools bug: a zero-delta text block between
        two tool_use blocks leaks into partials but is stripped from
        persistence.

        Expected shape (both should agree): just the two tools, no TextBlock.
        """
        current, persistence = self._feed_and_get_both_shapes(
            [
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.ts"}},
                {"type": "text", "text": ""},
                {"type": "tool_use", "id": "toolu_2", "name": "Read", "input": {"file_path": "b.ts"}},
            ]
        )
        assert tuple(current) == persistence

    def test_whitespace_only_text_between_tools_produces_equal_shapes(self) -> None:
        """A whitespace-only text delta (e.g. a single newline) survives
        ``split_text_and_media`` as a real TextBlock but is filtered from
        persistence. Partial and persistence must still agree."""
        current, persistence = self._feed_and_get_both_shapes(
            [
                {"type": "tool_use", "id": "toolu_1", "name": "Grep", "input": {"pattern": "foo"}},
                {"type": "text", "text": "\n"},
                {"type": "tool_use", "id": "toolu_2", "name": "Grep", "input": {"pattern": "bar"}},
            ]
        )
        assert tuple(current) == persistence

    def test_media_only_text_between_tools_produces_equal_shapes(self) -> None:
        """A text block whose content is entirely an ``<img>`` tag: the
        ``split_text_and_media`` path produces only a FileBlock, and the
        sentinel at the streaming index becomes ``TextBlock(text="")``.
        Partial and persistence must agree on the final shape."""
        current, persistence = self._feed_and_get_both_shapes(
            [
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.ts"}},
                {"type": "text", "text": "<img src='/tmp/a.png'>"},
                {"type": "tool_use", "id": "toolu_2", "name": "Read", "input": {"file_path": "b.ts"}},
            ]
        )
        assert tuple(current) == persistence

    def test_zero_delta_text_before_tools_produces_equal_shapes(self) -> None:
        """A zero-delta text block at the start of a turn (common pattern
        when the helpers default ``text_prefix=""``) must not leak into the
        final content via partials."""
        current, persistence = self._feed_and_get_both_shapes(
            [
                {"type": "text", "text": ""},
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.ts"}},
                {"type": "tool_use", "id": "toolu_2", "name": "Read", "input": {"file_path": "b.ts"}},
            ]
        )
        assert tuple(current) == persistence

    def test_contiguous_tools_without_any_text_produces_equal_shapes(self) -> None:
        """Baseline: multiple tools with no interleaved text should agree.
        This should pass today."""
        current, persistence = self._feed_and_get_both_shapes(
            [
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "a.ts"}},
                {"type": "tool_use", "id": "toolu_2", "name": "Read", "input": {"file_path": "b.ts"}},
                {"type": "tool_use", "id": "toolu_3", "name": "Read", "input": {"file_path": "c.ts"}},
            ]
        )
        assert tuple(current) == persistence


def _run_process_output(jsonl_dicts: list[dict]) -> list:
    """Feed JSONL dicts through the real ``_process_output`` loop and return emitted messages.

    Unlike ``_feed_jsonl`` (which mirrors only a subset of the dispatch), this
    pre-populates the process's stdout queue and runs the production
    ``_process_output`` method verbatim — so streamed-turn ChatMessage-ID
    assignment (the ``_streamed_turn_ids`` / ``_first_response_message_id``
    machinery) is exercised exactly as in production.
    """
    input_queue: Queue = Queue()
    for d in jsonl_dicts:
        input_queue.put((json.dumps(d), True))

    mock_process = MagicMock()
    mock_process.get_queue.return_value = input_queue
    # The loop exits once found_final_message is set AND the queue drains.
    mock_process.is_finished.return_value = True

    processor = ClaudeOutputProcessor(
        process=mock_process,
        source_command="test",
        output_message_queue=Queue(),
        environment=MagicMock(),
        diff_tracker=None,
        task_id=TaskID(),
        session_id_written_event=Event(),
        harness=CLAUDE_CODE_HARNESS,
        streaming_enabled=True,
    )
    processor._process_output()
    return _drain_queue(processor.output_message_queue)


def _collect_tool_ids(messages: Iterable) -> set[str]:
    """Return the set of tool_use ids reachable across the given chat messages."""
    tool_ids: set[str] = set()
    for message in messages:
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                tool_ids.add(block.id)
            elif isinstance(block, ToolResultBlock):
                tool_ids.add(block.tool_use_id)
    return tool_ids


class TestSubagentInterleavedTurnIds:
    """Regression tests for SCU-1421: chat dropping the majority of agent messages.

    When a subagent (Agent/Task tool) runs concurrently, its messages are
    delivered to the parent stream as NON-streamed ``assistant`` lines carrying
    a ``parent_tool_use_id``, interleaved with the main agent's own streamed
    turns (which all carry ``parent_tool_use_id == None``).

    ``_first_response_message_id`` (the stable ChatMessage ID for a streamed
    turn) is only regenerated when ``MessageStart`` sees the parent change vs
    ``_last_response_parent_tool_use_id``. That tracker was updated *only* by
    streamed ``MessageStart`` events, so an interleaved non-streamed subagent
    message left it stale — and the next main-agent turn (parent None ->
    None) reused the previous turn's ChatMessage ID. The frontend keys chat
    messages by ``id`` (``key={message.id}``), so colliding IDs overwrite each
    other and whole turns vanish from the chat.
    """

    @staticmethod
    def _main_streamed_turn(message_id: str, tool_id: str, text: str) -> list[dict]:
        """A normal streamed main-agent turn that issues one tool call.

        Includes the non-streaming ``assistant`` persistence line the CLI emits
        alongside the streamed events for the same turn.
        """
        return make_streaming_tool_events(
            message_id, [make_tool_use_block(tool_id, "Bash", {"cmd": text})], text_prefix=text
        ) + [make_assistant_message(message_id, [make_tool_use_block(tool_id, "Bash", {"cmd": text})])]

    def test_streamed_turn_after_subagent_message_gets_fresh_chat_message_id(self) -> None:
        """Two main-agent streamed turns separated by a non-streamed subagent
        message must NOT share a ``first_response_message_id``.

        Before the fix the subagent message left the parent tracker stale, so
        both turns reused one ID (``len(unique_ids) == 1``).
        """
        processor = _make_processor_for_jsonl_test()

        init = make_init_message(session_id="session_001")
        main_turn_a = make_streaming_text_events(message_id="msg_main_a", text="Main A")
        subagent_message = make_assistant_message(
            "msg_sub",
            [make_text_block("subagent working"), make_tool_use_block("toolu_sub", "Bash", {"cmd": "ls"})],
            parent_tool_use_id="toolu_agent",
        )
        main_turn_b = make_streaming_text_events(message_id="msg_main_b", text="Main B")

        _feed_jsonl(processor, [init] + main_turn_a + [subagent_message] + main_turn_b[:3])
        processor._emit_partial_message()

        partials = [
            m for m in _drain_queue(processor.output_message_queue) if isinstance(m, PartialResponseBlockAgentMessage)
        ]
        unique_ids = {p.first_response_message_id for p in partials}
        collapse_message = f"main-agent turns separated by a non-streamed subagent message reused one ChatMessage ID (got {len(unique_ids)} unique); the frontend would collapse them"
        assert len(unique_ids) == 2, collapse_message

    def test_interleaved_subagent_turns_do_not_collapse_in_chat(self) -> None:
        """End-to-end: main turns interleaved with concurrent subagent messages
        must each survive into the rendered chat.

        Reproduces the reported scenario (an Agent/Task subagent running while
        the main agent continues) and asserts that converting the emitted
        messages yields no duplicate ChatMessage IDs and preserves every tool
        call — i.e. the frontend (which keys by ``id``) shows all of them.
        """
        agent_tool, sub_tool, sub_tool_2 = "toolu_agent", "toolu_sub1", "toolu_sub2"
        main_tool_2, main_tool_3 = "toolu_main2", "toolu_main3"

        jsonl = [make_init_message("session_001")]
        # Main turn A launches a background subagent via the Task tool.
        jsonl += self._main_streamed_turn("msg_a", agent_tool, "launch")
        # Subagent (parent=agent_tool) runs concurrently; non-streamed lines
        # interleave with the main agent's own subsequent streamed turns.
        jsonl.append(
            make_assistant_message(
                "msg_sub1",
                [make_text_block("sub working"), make_tool_use_block(sub_tool, "Bash", {"cmd": "ls"})],
                parent_tool_use_id=agent_tool,
            )
        )
        jsonl += self._main_streamed_turn("msg_b", main_tool_2, "echo hi")
        jsonl.append(make_tool_result_message(main_tool_2, "hi"))
        jsonl.append(make_tool_result_message(sub_tool, "ls output", parent_tool_use_id=agent_tool))
        jsonl.append(
            make_assistant_message(
                "msg_sub2",
                [make_tool_use_block(sub_tool_2, "Bash", {"cmd": "pwd"})],
                parent_tool_use_id=agent_tool,
            )
        )
        jsonl += self._main_streamed_turn("msg_c", main_tool_3, "echo bye")
        jsonl.append(make_tool_result_message(main_tool_3, "bye"))
        jsonl.append(make_end_message("session_001"))

        emitted = _run_process_output(jsonl)

        request_id = AgentMessageID()
        stream = (
            [
                ChatInputUserMessage(message_id=request_id, text="/go", files=[]),
                RequestStartedAgentMessage(request_id=request_id),
            ]
            + emitted
            + [RequestSuccessAgentMessage(request_id=request_id)]
        )
        update = convert_agent_messages_to_task_update(stream, TaskID(), {}, CLAUDE_CODE_HARNESS)
        chat_messages = list(update.chat_messages)
        if update.in_progress_chat_message is not None:
            chat_messages.append(update.in_progress_chat_message)

        # No two ChatMessages may share an id — the frontend keys by id and a
        # collision silently drops a message.
        ids = [message.id for message in chat_messages]
        assert len(ids) == len(set(ids)), "duplicate ChatMessage ids would be dropped by the frontend"

        # Every tool the agent invoked must remain reachable after the frontend
        # collapses any same-id messages (last write wins).
        rendered_by_id = {message.id: message for message in chat_messages}
        visible_tool_ids = _collect_tool_ids(rendered_by_id.values())

        expected_tools = {agent_tool, sub_tool, sub_tool_2, main_tool_2, main_tool_3}
        assert expected_tools <= visible_tool_ids, "agent tool calls went missing from the chat"
