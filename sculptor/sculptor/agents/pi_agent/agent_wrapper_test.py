"""Tests for `PiAgent` — JSONL RPC exchange and start-time error surfaces.

The tests stub the pi subprocess with a `MagicMock` `RunningProcess` so
the full RPC pump can be exercised without a real binary. Coverage
mirrors pi's three-channel envelope: command-ACK `response`
events, `extension_ui_request` discards, and the `AgentSessionEvent`
session-stream.
"""

from __future__ import annotations

import json
from pathlib import Path
from queue import Queue
from typing import Any
from typing import Callable
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches_test import expect_exact_logged_errors
from imbue_core.sculptor.state.chat_state import AskUserQuestionData
from imbue_core.sculptor.state.chat_state import GenericToolContent
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.chat_state import ToolResultBlock
from imbue_core.sculptor.state.chat_state import ToolUseBlock
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.agents.pi_agent.agent_wrapper import PI_SESSION_DIR_NAME
from sculptor.agents.pi_agent.agent_wrapper import PI_SESSION_ID_STATE_FILE
from sculptor.agents.pi_agent.agent_wrapper import PiAgent
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.agents.pi_agent.output_processor import AgentMessage
from sculptor.agents.pi_agent.output_processor import ParsedUnknownEvent
from sculptor.agents.pi_agent.output_processor import extract_tool_call_blocks
from sculptor.agents.pi_agent.output_processor import parse_rpc_message
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.errors import PiBinaryNotFoundError
from sculptor.interfaces.agents.errors import PiCrashError
from sculptor.interfaces.agents.errors import PiVersionMismatchError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment

_PROMPT_ID = "prompt-1"


def _make_agent(
    environment: AgentExecutionEnvironment | None = None,
    on_diff_needed: Callable[[], None] | None = None,
) -> PiAgent:
    env = environment if environment is not None else MagicMock(spec=AgentExecutionEnvironment)
    return PiAgent(
        harness=PI_HARNESS,
        environment=env,
        task_id=TaskID(),
        config=PiAgentConfig(),
        system_prompt="",
        git_hash="deadbeef",
        on_diff_needed=on_diff_needed,
    )


def _make_process(lines: list[str], returncode: int = 0) -> MagicMock:
    """Stub `RunningProcess`: replays canned stdout lines then reports finished."""
    queue: Queue[tuple[str, bool]] = Queue()
    for line in lines:
        queue.put((line, True))

    process = MagicMock()
    process.get_queue.return_value = queue
    # is_finished() is polled inside the consume loop; report True only once
    # the queue has been drained.
    process.is_finished.side_effect = [False] * len(lines) + [True] * 50
    process.wait.return_value = returncode
    return process


def _event(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _assistant_msg(text: str, stop_reason: str = "stop") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stopReason": stop_reason,
    }


def _user_msg(text: str) -> dict[str, Any]:
    # A role="user" message carries no stopReason — pi only sets stopReason on
    # generated assistant messages. Mirrors the prompt-echo message pi emits at
    # the start of every agent run.
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _text_delta_update(delta: str, partial_text: str, content_index: int = 0) -> dict[str, Any]:
    return {
        "type": "message_update",
        "message": _assistant_msg(partial_text, stop_reason=""),
        "assistantMessageEvent": {
            "type": "text_delta",
            "contentIndex": content_index,
            "delta": delta,
        },
    }


def _tool_call_block(tool_call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    # pi's toolCall content block shape (docs/session-format.md): id, name, arguments.
    return {"type": "toolCall", "id": tool_call_id, "name": name, "arguments": arguments}


def _assistant_msg_with_content(content: list[dict[str, Any]], stop_reason: str = "toolUse") -> dict[str, Any]:
    return {"role": "assistant", "content": content, "stopReason": stop_reason}


def _tool_execution_start(tool_call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_execution_start", "toolCallId": tool_call_id, "toolName": name, "args": args}


def _tool_execution_end(tool_call_id: str, name: str, result: Any = None, is_error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool_execution_end",
        "toolCallId": tool_call_id,
        "toolName": name,
        "result": result,
        "isError": is_error,
    }


def _tool_use_blocks(messages: list) -> list[ToolUseBlock]:
    """Every ToolUseBlock across all emitted partial/response messages, in order."""
    return [block for m in messages for block in m.content if isinstance(block, ToolUseBlock)]


def _tool_result_blocks(messages: list) -> list[ToolResultBlock]:
    """Every ToolResultBlock across all emitted response messages, in order."""
    return [
        block
        for m in messages
        if isinstance(m, ResponseBlockAgentMessage)
        for block in m.content
        if isinstance(block, ToolResultBlock)
    ]


def _generic_result_text(block: ToolResultBlock) -> str:
    """Narrow a result block's content to GenericToolContent and return its text."""
    assert isinstance(block.content, GenericToolContent)
    return block.content.text


def _text_block_text(block: object) -> str:
    """Narrow a content block to TextBlock and return its text."""
    assert isinstance(block, TextBlock)
    return block.text


def test_text_delta_accumulates_into_partial_blocks() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("hello ", "hello ")),
            _event(_text_delta_update("world", "hello world")),
            _event({"type": "agent_end", "messages": [_assistant_msg("hello world")], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    emitted = _drain(agent._output_messages)
    partials = [m for m in emitted if isinstance(m, PartialResponseBlockAgentMessage)]
    snapshots = [block.text for partial in partials for block in partial.content if isinstance(block, TextBlock)]
    assert snapshots == ["hello ", "hello world"]


def test_message_end_finalizes_response_block_with_partial_ids() -> None:
    """The final ResponseBlock reuses the partial's `assistant_message_id` so the UI collapses them."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("done.", "done.")),
            _event({"type": "message_end", "message": _assistant_msg("done.")}),
            _event({"type": "agent_end", "messages": [_assistant_msg("done.")], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    emitted = _drain(agent._output_messages)
    partials = [m for m in emitted if isinstance(m, PartialResponseBlockAgentMessage)]
    finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
    assert len(finals) == 1
    assert finals[0].role == "assistant"
    assert finals[0].content == (TextBlock(text="done."),)
    # ID coherence: the final must share the partial's IDs so the UI's stable-id
    # collapse can fold partial-then-final into one chat row.
    assert partials, "partials must have been emitted for IDs to match"
    assert finals[0].assistant_message_id == partials[-1].assistant_message_id
    assert finals[0].message_id == partials[-1].first_response_message_id


def test_user_role_message_end_is_not_echoed_as_assistant_response() -> None:
    """pi records the user's own prompt as a role="user" message_end before the assistant streams.

    That user-role message_end must be dropped: only assistant messages carry generated
    text to surface. Otherwise the user's prompt is reflected back as an assistant chat
    bubble at the start of every turn.
    """
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "response", "command": "prompt", "success": True, "id": _PROMPT_ID}),
            _event({"type": "agent_start"}),
            # pi echoes the prompt back as a role="user" message_end here.
            _event({"type": "message_end", "message": _user_msg("who are you?")}),
            _event(_text_delta_update("I am Sculptor.", "I am Sculptor.")),
            _event({"type": "message_end", "message": _assistant_msg("I am Sculptor.")}),
            _event({"type": "agent_end", "messages": [_assistant_msg("I am Sculptor.")], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    emitted = _drain(agent._output_messages)
    finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
    assert len(finals) == 1
    assert finals[0].content == (TextBlock(text="I am Sculptor."),)


def test_agent_end_finalizes_from_accumulator_when_message_end_did_not_fire() -> None:
    """If pi closes the run without a message_end (e.g. abort), agent_end emits the accumulated text."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("partial-only", "partial-only")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    emitted = _drain(agent._output_messages)
    finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
    assert len(finals) == 1
    assert finals[0].content == (TextBlock(text="partial-only"),)


def test_consume_terminates_on_agent_end() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [_event({"type": "agent_end", "messages": [], "willRetry": False})],
    )
    # Must return without hanging.
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_message_end_is_not_a_turn_boundary_when_tool_loop_continues() -> None:
    """Multiple message_end events inside one agent run (tool-loop scenario) do not yield the turn."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("thinking", "thinking")),
            _event({"type": "message_end", "message": _assistant_msg("thinking", stop_reason="toolUse")}),
            _event({"type": "tool_execution_start", "toolCallId": "t1", "toolName": "read", "args": {}}),
            _event(
                {"type": "tool_execution_end", "toolCallId": "t1", "toolName": "read", "result": {}, "isError": False}
            ),
            _event(_text_delta_update("done.", "done.")),
            _event({"type": "message_end", "message": _assistant_msg("done.")}),
            _event(
                {
                    "type": "agent_end",
                    "messages": [
                        _assistant_msg("thinking", stop_reason="toolUse"),
                        _assistant_msg("done."),
                    ],
                    "willRetry": False,
                }
            ),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)

    emitted = _drain(agent._output_messages)
    finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
    texts = [block.text for f in finals for block in f.content if isinstance(block, TextBlock)]
    # Both assistant messages with text are emitted at agent_end.
    assert texts == ["thinking", "done."]


def test_response_with_success_false_on_prompt_raises_pi_crash_error() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event(
                {
                    "type": "response",
                    "command": "prompt",
                    "success": False,
                    "id": _PROMPT_ID,
                    "error": "No API key found",
                }
            ),
        ]
    )
    with pytest.raises(PiCrashError) as exc_info:
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    assert "No API key found" in str(exc_info.value)


def test_response_success_true_does_not_terminate_turn() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "response", "command": "prompt", "success": True, "id": _PROMPT_ID}),
            _event({"type": "agent_start"}),
            _event(_text_delta_update("hi", "hi")),
            _event({"type": "agent_end", "messages": [_assistant_msg("hi")], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    emitted = _drain(agent._output_messages)
    finals = [m for m in emitted if isinstance(m, ResponseBlockAgentMessage)]
    assert len(finals) == 1


def test_response_for_other_prompt_id_is_ignored() -> None:
    """Out-of-band responses (e.g. parse errors with no id) do not raise."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "response", "command": "parse", "success": False, "error": "bad json"}),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_in_stream_assistant_message_error_raises_pi_crash_error() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("partial ", "partial ")),
            _event(
                {
                    "type": "message_update",
                    "message": _assistant_msg("partial ", stop_reason=""),
                    "assistantMessageEvent": {"type": "error", "reason": "upstream model failed"},
                }
            ),
        ]
    )
    with pytest.raises(PiCrashError) as exc_info:
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    # Accumulated text is preserved in the surfaced error text.
    assert "partial" in str(exc_info.value) or "upstream" in str(exc_info.value)


def test_message_end_with_error_stop_reason_raises_pi_crash_error() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event({"type": "message_end", "message": _assistant_msg("oops", stop_reason="error")}),
        ]
    )
    with pytest.raises(PiCrashError):
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_agent_end_with_aborted_message_raises_pi_crash_error() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event(
                {
                    "type": "agent_end",
                    "messages": [_assistant_msg("partial", stop_reason="aborted")],
                    "willRetry": False,
                }
            ),
        ]
    )
    with pytest.raises(PiCrashError):
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_auto_retry_end_failure_raises_pi_crash_error() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event(
                {
                    "type": "auto_retry_end",
                    "success": False,
                    "attempt": 3,
                    "finalError": "rate limited after 3 attempts",
                }
            ),
        ]
    )
    with pytest.raises(PiCrashError) as exc_info:
        agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    assert "rate limited" in str(exc_info.value)


def test_auto_retry_end_success_does_not_yield_turn() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "auto_retry_end", "success": True, "attempt": 2}),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_tool_call_renders_use_block_while_running_and_result_when_done() -> None:
    """A read tool call: the issuing message's toolCall block becomes a ToolUseBlock
    (name + input, shown while running) and tool_execution_end becomes its result."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("Reading. ", "Reading. ")),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content(
                        [
                            {"type": "text", "text": "Reading. "},
                            _tool_call_block("t1", "read", {"path": "/repo/a.txt"}),
                        ]
                    ),
                }
            ),
            _event(_tool_execution_start("t1", "read", {"path": "/repo/a.txt"})),
            _event(
                {
                    "type": "tool_execution_update",
                    "toolCallId": "t1",
                    "toolName": "read",
                    "args": {"path": "/repo/a.txt"},
                    "partialResult": {"content": [{"type": "text", "text": "file contents"}]},
                }
            ),
            _event(_tool_execution_end("t1", "read", result={"content": [{"type": "text", "text": "file contents"}]})),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    emitted = _drain(agent._output_messages)

    # While running: a ToolUseBlock with the mapped Claude name + adapted input.
    use_blocks = _tool_use_blocks(emitted)
    assert any(b.id == "t1" and b.name == "Read" and b.input == {"file_path": "/repo/a.txt"} for b in use_blocks)
    # When done: a ToolResultBlock correlated by id, non-error, with result text.
    result_blocks = _tool_result_blocks(emitted)
    assert len(result_blocks) == 1
    result = result_blocks[0]
    assert result.tool_use_id == "t1"
    assert result.tool_name == "Read"
    assert result.is_error is False
    assert isinstance(result.content, GenericToolContent)
    assert result.content.text == "file contents"


@pytest.mark.parametrize(
    "pi_name, pi_args, claude_name, claude_input",
    [
        ("read", {"path": "/r.txt"}, "Read", {"file_path": "/r.txt"}),
        ("write", {"path": "/w.txt", "content": "x"}, "Write", {"file_path": "/w.txt", "content": "x"}),
        ("bash", {"command": "ls"}, "Bash", {"command": "ls"}),
        (
            "edit",
            {"path": "/e.txt", "edits": [{"oldText": "a", "newText": "b"}]},
            "Edit",
            {"file_path": "/e.txt", "old_string": "a", "new_string": "b"},
        ),
    ],
)
def test_core_tool_use_block_maps_name_and_input(
    pi_name: str, pi_args: dict[str, Any], claude_name: str, claude_input: dict[str, Any]
) -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content([_tool_call_block("t1", pi_name, pi_args)]),
                }
            ),
            _event(_tool_execution_end("t1", pi_name, result="ok")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    emitted = _drain(agent._output_messages)
    use_blocks = _tool_use_blocks(emitted)
    assert any(b.id == "t1" and b.name == claude_name and b.input == claude_input for b in use_blocks)


def test_multi_edit_tool_renders_as_multiedit() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content(
                        [
                            _tool_call_block(
                                "t1",
                                "edit",
                                {
                                    "path": "/e.txt",
                                    "edits": [
                                        {"oldText": "a", "newText": "b"},
                                        {"oldText": "c", "newText": "d"},
                                    ],
                                },
                            )
                        ]
                    ),
                }
            ),
            _event(_tool_execution_end("t1", "edit", result="ok")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    use_blocks = _tool_use_blocks(_drain(agent._output_messages))
    block = next(b for b in use_blocks if b.id == "t1")
    assert block.name == "MultiEdit"
    assert block.input == {
        "file_path": "/e.txt",
        "edits": [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": "d"}],
    }


def test_unknown_tool_renders_generically_unmapped() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content(
                        [_tool_call_block("t1", "frobnicate", {"widget": "gadget"})]
                    ),
                }
            ),
            _event(_tool_execution_end("t1", "frobnicate", result="done")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    use_blocks = _tool_use_blocks(_drain(agent._output_messages))
    block = next(b for b in use_blocks if b.id == "t1")
    # Unknown tools pass through unmapped (rendered generically by the frontend).
    assert block.name == "frobnicate"
    assert block.input == {"widget": "gadget"}


def test_text_tool_text_interleaving_in_one_message() -> None:
    """Final content preserves the order text → tool → text within one assistant message."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content(
                        [
                            {"type": "text", "text": "before"},
                            _tool_call_block("t1", "bash", {"command": "ls"}),
                            {"type": "text", "text": "after"},
                        ]
                    ),
                }
            ),
            _event(_tool_execution_end("t1", "bash", result="output")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    finals = [m for m in _drain(agent._output_messages) if isinstance(m, ResponseBlockAgentMessage)]
    # The finalized assistant message interleaves text, tool use, text in order.
    interleaved = next(f for f in finals if any(isinstance(b, ToolUseBlock) for b in f.content))
    kinds = [type(b).__name__ for b in interleaved.content]
    assert kinds == ["TextBlock", "ToolUseBlock", "TextBlock"]
    assert _text_block_text(interleaved.content[0]) == "before"
    assert _text_block_text(interleaved.content[2]) == "after"


def test_error_result_renders_as_error() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content([_tool_call_block("t1", "read", {"path": "/missing"})]),
                }
            ),
            _event(_tool_execution_end("t1", "read", result="ENOENT: no such file", is_error=True)),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    result_blocks = _tool_result_blocks(_drain(agent._output_messages))
    assert len(result_blocks) == 1
    assert result_blocks[0].is_error is True
    assert _generic_result_text(result_blocks[0]) == "ENOENT: no such file"


def test_in_message_toolcall_and_lane_start_reconcile_to_one_block() -> None:
    """A toolCall content block and the lane's tool_execution_start with the same
    id are the SAME call — the ToolUseBlock is rendered once (from message_end),
    and tool_execution_start does not render a duplicate."""
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "agent_start"}),
            _event(_text_delta_update("x", "x")),
            _event(
                {
                    "type": "message_end",
                    "message": _assistant_msg_with_content(
                        [{"type": "text", "text": "x"}, _tool_call_block("t1", "read", {"path": "/a"})]
                    ),
                }
            ),
            _event(_tool_execution_start("t1", "read", {"path": "/a"})),
            _event(_tool_execution_end("t1", "read", result="ok")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    emitted = _drain(agent._output_messages)
    # Exactly one partial introduces the ToolUseBlock for t1 (message_end's); the
    # lane's start for the already-registered id emits no further partial.
    partials_with_t1 = [
        m
        for m in emitted
        if isinstance(m, PartialResponseBlockAgentMessage)
        and any(isinstance(b, ToolUseBlock) and b.id == "t1" for b in m.content)
    ]
    assert len(partials_with_t1) == 1
    # And exactly one result block.
    assert len(_tool_result_blocks(emitted)) == 1


def test_orphan_lane_tool_renders_from_start_when_no_toolcall_block() -> None:
    """A lane event with no matching toolCall block (not expected from real pi)
    still renders — tool_execution_start creates the ToolUseBlock so the call is
    never silently dropped; a read tool fires no diff refresh."""
    on_diff_needed = MagicMock()
    agent = _make_agent(on_diff_needed=on_diff_needed)
    agent._process = _make_process(
        [
            _event(_tool_execution_start("t1", "read", {"path": "/a"})),
            _event(_tool_execution_end("t1", "read", result="contents")),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    emitted = _drain(agent._output_messages)
    assert any(b.id == "t1" and b.name == "Read" for b in _tool_use_blocks(emitted))
    result_blocks = _tool_result_blocks(emitted)
    assert len(result_blocks) == 1
    assert _generic_result_text(result_blocks[0]) == "contents"
    on_diff_needed.assert_not_called()


@pytest.mark.parametrize("tool_name", ["edit", "write", "bash"])
def test_file_change_tool_execution_end_refreshes_diff(tool_name: str) -> None:
    """A successful edit/write/bash tool triggers a single workspace-diff refresh."""
    on_diff_needed = MagicMock()
    agent = _make_agent(on_diff_needed=on_diff_needed)
    agent._process = _make_process(
        [
            _event({"type": "tool_execution_start", "toolCallId": "t1", "toolName": tool_name, "args": {}}),
            _event(
                {
                    "type": "tool_execution_end",
                    "toolCallId": "t1",
                    "toolName": tool_name,
                    "result": {},
                    "isError": False,
                }
            ),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    on_diff_needed.assert_called_once()


def test_errored_file_change_tool_execution_end_does_not_refresh_diff() -> None:
    """A failed file-mutating tool (isError) must not refresh the diff."""
    on_diff_needed = MagicMock()
    agent = _make_agent(on_diff_needed=on_diff_needed)
    agent._process = _make_process(
        [
            _event(
                {
                    "type": "tool_execution_end",
                    "toolCallId": "t1",
                    "toolName": "edit",
                    "result": {},
                    "isError": True,
                }
            ),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    on_diff_needed.assert_not_called()


def test_extension_ui_request_is_discarded() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event({"type": "extension_ui_request", "id": "ui-1", "method": "select", "options": []}),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_extension_error_is_logged_and_non_terminal() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event(
                {
                    "type": "extension_error",
                    "extensionPath": "/ext",
                    "event": "some-callback",
                    "error": "ext threw",
                }
            ),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    # Must not raise; must reach agent_end.
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_consume_ignores_non_json_and_unknown_event_types() -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            "not json at all",
            _event({"type": "queue_update", "steering": [], "followUp": []}),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)


def test_send_rpc_writes_json_line_to_stdin() -> None:
    agent = _make_agent()
    fake_process = MagicMock()
    agent._process = fake_process
    agent._send_rpc({"type": "prompt", "id": "p1", "message": "hi"})
    fake_process.write_stdin.assert_called_once()
    written = fake_process.write_stdin.call_args.args[0]
    assert json.loads(written.rstrip("\n")) == {"type": "prompt", "id": "p1", "message": "hi"}


def test_push_message_enqueues_chat_input_returns_true() -> None:
    agent = _make_agent()
    chat = ChatInputUserMessage(text="hi")
    assert agent._push_message(chat) is True
    assert agent._input_agent_messages.get_nowait() is chat


# The capability-correlated control messages pi cannot handle; each must be
# dead-lettered (one logged error) and return unhandled.
# ResumeAgentResponseRunnerMessage is NOT here — it is now handled (see
# test_push_message_resume_resolves_in_flight_request).
_DEAD_LETTER_MESSAGES: list[Message] = [
    ClearContextUserMessage(),
    InterruptProcessUserMessage(),
    UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"q": "a"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    ),
]


@pytest.mark.parametrize("message", _DEAD_LETTER_MESSAGES, ids=lambda m: type(m).__name__)
def test_push_message_dead_letters_unsupported_control_messages(message: Message) -> None:
    agent = _make_agent()
    # The dead-letter is logged at error level; the test harness intercepts and
    # accumulates it. `expect_exact_logged_errors` asserts exactly one error is
    # logged whose template carries the dead-letter text (the concrete message
    # type is interpolated into the log args, which this harness does not match
    # on — the per-type coverage comes from the parametrization).
    with expect_exact_logged_errors(["PiAgent dropping unsupported control message"]):
        handled = agent._push_message(message)
    # Returns False so base-class generic handling still runs.
    assert handled is False


def test_push_message_does_not_dead_letter_base_class_handled_types() -> None:
    """StopAgentUserMessage is handled by the base class after the False return, so it must NOT log a dead-letter error here."""
    agent = _make_agent()
    with expect_exact_logged_errors([]):
        handled = agent._push_message(StopAgentUserMessage())
    assert handled is False


def test_push_message_resume_resolves_in_flight_request() -> None:
    """A resume message resolves the orphaned in-flight request so the UI unsticks.

    The previous process died mid-turn leaving the original chat message with a
    RequestStarted but no terminal RequestSuccess. PiAgent handles the resume by
    emitting RequestSuccess for that ORIGINAL message id (for_user_message_id),
    marked interrupted — no dead-letter error, returns handled.
    """
    agent = _make_agent()
    stuck_id = AgentMessageID()
    with expect_exact_logged_errors([]):
        handled = agent._push_message(ResumeAgentResponseRunnerMessage(for_user_message_id=stuck_id))
    assert handled is True
    emitted = agent._output_messages.get_nowait()
    assert isinstance(emitted, RequestSuccessAgentMessage)
    assert emitted.request_id == stuck_id
    assert emitted.interrupted is True


def _make_start_env(persisted_session_id: str | None = None) -> MagicMock:
    """A MagicMock environment that lets PiAgent.start() run past the binary /
    version preflight and into the session-launch logic.

    `persisted_session_id` None ⇒ the pi_session_id state file is absent (fresh
    launch); a value ⇒ it is present (resume launch).
    """
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_tool_binary_path.return_value = "/bin/pi"
    version_result = MagicMock()
    version_result.stdout = ""
    version_result.stderr = "pi 0.78.0\n"
    env.run_process_to_completion.return_value = version_result
    env.get_state_path.return_value = Path("/fake/state")
    env.get_system_prompt.return_value = ""

    def _read_file(path: str, mode: str = "r") -> str:
        if path.endswith(PI_SESSION_ID_STATE_FILE) and persisted_session_id is not None:
            return persisted_session_id
        # removed_message_ids (base class) and an absent pi_session_id both miss.
        raise FileNotFoundError(path)

    env.read_file.side_effect = _read_file
    env.run_process_in_background.return_value = MagicMock()
    return env


def _launched_command(env: MagicMock) -> list[str]:
    env.run_process_in_background.assert_called_once()
    return list(env.run_process_in_background.call_args.args[0])


def test_start_fresh_session_mints_and_persists_id_with_session_flags() -> None:
    env = _make_start_env(persisted_session_id=None)
    agent = _make_agent(env)
    with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", return_value="sess-fresh-1"):
        agent.start(secrets={})
    command = _launched_command(env)
    # The old ephemeral flag is gone; a per-task session dir + Sculptor-pinned id ship instead.
    assert "--no-session" not in command
    assert "--session-dir" in command
    assert command[command.index("--session-dir") + 1] == str(Path("/fake/state") / PI_SESSION_DIR_NAME)
    assert "--session-id" in command
    assert command[command.index("--session-id") + 1] == "sess-fresh-1"
    # The minted id is persisted up front so a crash during the first turn still leaves a resumable id.
    env.write_file.assert_called_once_with(str(Path("/fake/state") / PI_SESSION_ID_STATE_FILE), "sess-fresh-1")


def test_start_resume_reuses_persisted_id_and_verifies_without_rewriting() -> None:
    env = _make_start_env(persisted_session_id="resume-7")
    agent = _make_agent(env)
    with patch.object(agent, "_verify_resumed_session") as mock_verify:
        agent.start(secrets={})
    command = _launched_command(env)
    assert command[command.index("--session-id") + 1] == "resume-7"
    # Resume must NOT re-persist (the id is unchanged) and MUST verify the resume.
    env.write_file.assert_not_called()
    mock_verify.assert_called_once_with("resume-7")


def test_verify_resumed_session_logs_loud_on_empty_session() -> None:
    """An empty session on a resume launch means the on-disk file was lost — log loud."""
    agent = _make_agent()
    with patch.object(agent, "_request_state_blocking", return_value={"sessionId": "abc", "messageCount": 0}):
        with expect_exact_logged_errors(["PiAgent expected to resume pi session"]):
            agent._verify_resumed_session("abc")


def test_verify_resumed_session_logs_loud_on_session_id_mismatch() -> None:
    agent = _make_agent()
    with patch.object(agent, "_request_state_blocking", return_value={"sessionId": "other", "messageCount": 3}):
        with expect_exact_logged_errors(["PiAgent resume mismatch"]):
            agent._verify_resumed_session("abc")


def test_verify_resumed_session_logs_loud_when_no_state_response() -> None:
    agent = _make_agent()
    with patch.object(agent, "_request_state_blocking", return_value=None):
        with expect_exact_logged_errors(["PiAgent could not verify resumed pi session"]):
            agent._verify_resumed_session("abc")


def test_verify_resumed_session_ok_logs_no_error() -> None:
    agent = _make_agent()
    with patch.object(agent, "_request_state_blocking", return_value={"sessionId": "abc", "messageCount": 4}):
        with expect_exact_logged_errors([]):
            agent._verify_resumed_session("abc")


def test_request_state_blocking_returns_session_state_from_matching_response() -> None:
    agent = _make_agent()
    response = _event(
        {
            "type": "response",
            "command": "get_state",
            "success": True,
            "id": "rs-req",
            "data": {"sessionId": "abc", "messageCount": 3},
        }
    )
    agent._process = _make_process([response])
    with patch("sculptor.agents.pi_agent.agent_wrapper.generate_id", return_value="rs-req"):
        state = agent._request_state_blocking(timeout=2.0)
    assert state == {"sessionId": "abc", "messageCount": 3}


def test_start_raises_pi_binary_not_found_when_path_unresolved() -> None:
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_tool_binary_path.return_value = None
    agent = _make_agent(env)
    with pytest.raises(PiBinaryNotFoundError):
        agent.start(secrets={})


def test_start_raises_pi_version_mismatch_when_out_of_range() -> None:
    env = MagicMock(spec=AgentExecutionEnvironment)
    env.get_tool_binary_path.return_value = "/bin/pi"
    version_result = MagicMock()
    # Real pi emits --version to stderr (not stdout), so route it there.
    version_result.stdout = ""
    version_result.stderr = "pi 0.50.0\n"
    env.run_process_to_completion.return_value = version_result
    agent = _make_agent(env)
    with pytest.raises(PiVersionMismatchError) as exc_info:
        agent.start(secrets={})
    assert exc_info.value.pinned_version == "0.78.0"
    assert exc_info.value.detected_version == "0.50.0"


def test_check_pi_version_reads_version_from_stderr_only_emission() -> None:
    """Real pi emits --version to stderr; the version probe must read both channels."""
    env = MagicMock(spec=AgentExecutionEnvironment)
    version_result = MagicMock()
    version_result.stdout = ""
    version_result.stderr = "0.78.0\n"
    env.run_process_to_completion.return_value = version_result
    agent = _make_agent(env)

    detected = agent._check_pi_version("/bin/pi")

    assert detected == "0.78.0"


def _drain(queue: Queue) -> list:
    out: list = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


# --- Typed protocol module: parse + dispatch coverage ----------------------

# Wire-shape fixtures for every documented event type (RPC §5/§7/§9), lifted
# from the protocol doc's examples. Each must parse to a typed variant whose
# discriminator matches.
_DOCUMENTED_EVENTS: list[dict[str, Any]] = [
    {"type": "response", "command": "prompt", "success": True, "id": _PROMPT_ID},
    {"type": "extension_ui_request", "id": "u1", "method": "select"},
    {"type": "agent_start"},
    {"type": "agent_end", "messages": [], "willRetry": False},
    {"type": "turn_start"},
    {"type": "turn_end", "message": _assistant_msg("x"), "toolResults": []},
    {"type": "message_start", "message": _assistant_msg("x", stop_reason="")},
    _text_delta_update("x", "x"),
    {"type": "message_end", "message": _assistant_msg("x")},
    {"type": "tool_execution_start", "toolCallId": "t", "toolName": "read", "args": {}},
    {"type": "tool_execution_update", "toolCallId": "t", "toolName": "read", "args": {}, "partialResult": "..."},
    {"type": "tool_execution_end", "toolCallId": "t", "toolName": "read", "result": {}, "isError": False},
    {"type": "queue_update", "steering": [], "followUp": []},
    {"type": "compaction_start", "reason": "threshold"},
    {"type": "compaction_end", "reason": "threshold", "aborted": False, "willRetry": False},
    {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3, "delayMs": 100, "errorMessage": "x"},
    {"type": "auto_retry_end", "success": True, "attempt": 1},
    {"type": "session_info_changed", "name": "sess"},
    {"type": "thinking_level_changed", "level": "high"},
    {"type": "extension_error", "extensionPath": "/x", "event": "e", "error": "boom"},
]


@pytest.mark.parametrize("payload", _DOCUMENTED_EVENTS, ids=lambda p: str(p["type"]))
def test_parse_rpc_message_types_each_documented_event(payload: dict[str, Any]) -> None:
    parsed = parse_rpc_message(payload)
    assert not isinstance(parsed, ParsedUnknownEvent), f"{payload['type']} should parse to a typed model"
    assert parsed.type == payload["type"]


def test_parse_rpc_message_returns_unknown_for_unrecognized_type() -> None:
    payload = {"type": "from_the_future", "data": 1}
    parsed = parse_rpc_message(payload)
    assert isinstance(parsed, ParsedUnknownEvent)
    assert parsed.raw == payload


def test_parse_rpc_message_returns_unknown_for_missing_or_malformed_shape() -> None:
    # No discriminator at all, and a known type whose required field is absent.
    assert isinstance(parse_rpc_message({"no": "type"}), ParsedUnknownEvent)
    assert isinstance(parse_rpc_message({"type": "message_update"}), ParsedUnknownEvent)


# Events pi-basic does not consume: each must be discarded (no emitted message,
# no PiCrashError), and the turn must still end at the following agent_end.
_DISCARDED_EVENTS: list[dict[str, Any]] = [
    {"type": "turn_start"},
    {"type": "turn_end", "message": _assistant_msg("x"), "toolResults": []},
    {"type": "message_start", "message": _assistant_msg("x", stop_reason="")},
    {"type": "queue_update", "steering": ["a"], "followUp": []},
    {"type": "compaction_start", "reason": "threshold"},
    {"type": "compaction_end", "reason": "threshold", "aborted": False, "willRetry": False},
    {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3, "delayMs": 1, "errorMessage": "e"},
    {"type": "session_info_changed", "name": "s"},
    {"type": "thinking_level_changed", "level": "high"},
    {"type": "from_the_future"},
]


@pytest.mark.parametrize("payload", _DISCARDED_EVENTS, ids=lambda p: str(p["type"]))
def test_unconsumed_event_is_discarded_and_turn_still_ends(payload: dict[str, Any]) -> None:
    agent = _make_agent()
    agent._process = _make_process(
        [
            _event(payload),
            _event({"type": "agent_end", "messages": [], "willRetry": False}),
        ]
    )
    # Must not raise and must not hang — the agent_end terminates the turn.
    agent._consume_until_turn_end(prompt_id=_PROMPT_ID)
    assert not _drain(agent._output_messages)


def test_extract_tool_call_blocks_returns_only_tool_call_blocks() -> None:
    message = AgentMessage(
        role="assistant",
        content=[
            {"type": "text", "text": "hi"},
            {"type": "toolCall", "toolName": "read", "args": {}},
        ],
    )
    blocks = extract_tool_call_blocks(message)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "toolCall"
