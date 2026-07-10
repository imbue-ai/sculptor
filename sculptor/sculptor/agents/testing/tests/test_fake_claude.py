"""Unit tests for FakeClaude script."""

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from typing import IO
from uuid import uuid4

import pytest

from sculptor.agents.testing.fake_claude import _parse_prompt
from sculptor.agents.testing.fake_claude import _read_prompt_from_stream_json_stdin
from sculptor.agents.testing.fake_claude_commands import _ABSORBED_FRAMES
from sculptor.agents.testing.fake_claude_commands import _STDIN_EOF
from sculptor.agents.testing.fake_claude_commands import _STDIN_ROUTER
from sculptor.agents.testing.fake_claude_commands import _read_mcp_control_response_text
from sculptor.agents.testing.fake_claude_commands import _read_mcp_control_responses
from sculptor.agents.testing.fake_claude_commands import configure_stdin_router
from sculptor.agents.testing.fake_claude_commands import handle_ask_user_question
from sculptor.agents.testing.fake_claude_commands import handle_background_task_notification
from sculptor.agents.testing.fake_claude_commands import handle_background_task_started
from sculptor.agents.testing.fake_claude_commands import handle_bash
from sculptor.agents.testing.fake_claude_commands import handle_default
from sculptor.agents.testing.fake_claude_commands import handle_edit_file
from sculptor.agents.testing.fake_claude_commands import handle_multi_step
from sculptor.agents.testing.fake_claude_commands import handle_parallel_tools
from sculptor.agents.testing.fake_claude_commands import handle_stream_text
from sculptor.agents.testing.fake_claude_commands import handle_task_create
from sculptor.agents.testing.fake_claude_commands import handle_task_update
from sculptor.agents.testing.fake_claude_commands import handle_text
from sculptor.agents.testing.fake_claude_commands import handle_wait_for_file
from sculptor.agents.testing.fake_claude_commands import handle_write_file
from sculptor.agents.testing.fake_claude_jsonl import generate_id
from sculptor.agents.testing.fake_claude_jsonl import make_assistant_message
from sculptor.agents.testing.fake_claude_jsonl import make_end_message
from sculptor.agents.testing.fake_claude_jsonl import make_init_message
from sculptor.agents.testing.fake_claude_jsonl import make_queued_command_attachment_entry
from sculptor.agents.testing.fake_claude_jsonl import make_task_notification_message
from sculptor.agents.testing.fake_claude_jsonl import make_task_started_message
from sculptor.agents.testing.fake_claude_jsonl import make_text_block
from sculptor.agents.testing.fake_claude_jsonl import make_tool_result_message
from sculptor.agents.testing.fake_claude_jsonl import make_tool_use_block
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.claude_state import ParsedAssistantResponse
from sculptor.state.claude_state import ParsedEndResponse
from sculptor.state.claude_state import ParsedInitResponse
from sculptor.state.claude_state import ParsedTaskNotificationResponse
from sculptor.state.claude_state import ParsedTaskStartedResponse
from sculptor.state.claude_state import ParsedToolResultResponseSimple
from sculptor.state.claude_state import parse_claude_code_json_lines_simple


@pytest.fixture(autouse=True)
def _reset_stdin_router() -> Iterator[None]:
    """Clear the module-level stdin router between tests.

    The router is a process-wide singleton whose buffer/EOF state persists
    across tests in one pytest process; resetting keeps a prior test's leftover
    bytes or EOF from leaking into the next reader.
    """
    _STDIN_ROUTER.reset()
    _ABSORBED_FRAMES.clear()
    yield
    _STDIN_ROUTER.reset()
    _ABSORBED_FRAMES.clear()


def test_init_message_roundtrip() -> None:
    session_id = f"test-{uuid4().hex}"
    msg = make_init_message(session_id)
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "system"
    assert isinstance(parsed, ParsedInitResponse)
    assert parsed.session_id == session_id
    assert len(parsed.tools) > 0
    assert parsed.mcp_servers == {}


def test_init_message_advertises_task_tools() -> None:
    msg = make_init_message(f"test-{uuid4().hex}")
    tools = msg["tools"]
    assert "TaskCreate" in tools
    assert "TaskUpdate" in tools
    assert "TaskList" in tools
    assert "TaskGet" in tools
    assert "TodoWrite" not in tools


def test_task_started_message_roundtrip() -> None:
    msg = make_task_started_message(
        task_id="task-123",
        tool_use_id="toolu-456",
        description="Run tests",
        task_type="local_bash",
    )
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "system"
    assert isinstance(parsed, ParsedTaskStartedResponse)
    assert parsed.task_id == "task-123"
    assert parsed.tool_use_id == "toolu-456"
    assert parsed.description == "Run tests"
    assert parsed.task_type == "local_bash"


def test_task_notification_message_roundtrip() -> None:
    msg = make_task_notification_message(
        task_id="task-123",
        tool_use_id="toolu-456",
        status="completed",
        summary="Tests passed",
    )
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "system"
    assert isinstance(parsed, ParsedTaskNotificationResponse)
    assert parsed.task_id == "task-123"
    assert parsed.tool_use_id == "toolu-456"
    assert parsed.status == "completed"
    assert parsed.summary == "Tests passed"


def test_task_notification_message_without_tool_use_id_parses() -> None:
    """A task_notification missing tool_use_id must parse, not raise KeyError.

    The CLI omits tool_use_id when a background task orphaned by a process exit
    is reported as failed on resume (see SCU-1666). Parsing must degrade to an
    empty tool_use_id instead of crashing the agent's output-processing thread.
    """
    msg = make_task_notification_message(
        task_id="task-123",
        tool_use_id=None,
        status="failed",
        summary="Background task did not complete",
    )
    assert "tool_use_id" not in msg
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    _msg_type, parsed = result
    assert isinstance(parsed, ParsedTaskNotificationResponse)
    assert parsed.task_id == "task-123"
    assert parsed.tool_use_id == ""
    assert parsed.status == "failed"


def test_task_started_message_without_tool_use_id_parses() -> None:
    """task_started tolerates a missing tool_use_id too (parity with task_notification).

    The notification handler is where the orphaned-on-restart payload actually
    drops the key, but task_started reads it the same defensive way, so a variant
    payload there must degrade to an empty id rather than crashing the agent.
    """
    msg = make_task_started_message(
        task_id="task-123",
        tool_use_id="toolu-456",
        description="Run tests",
        task_type="local_bash",
    )
    del msg["tool_use_id"]
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    _msg_type, parsed = result
    assert isinstance(parsed, ParsedTaskStartedResponse)
    assert parsed.task_id == "task-123"
    assert parsed.tool_use_id == ""


def test_assistant_text_message_roundtrip() -> None:
    msg_id = f"msg-{uuid4().hex}"
    msg = make_assistant_message(msg_id, [make_text_block("hello")])
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "assistant"
    assert isinstance(parsed, ParsedAssistantResponse)
    assert len(parsed.content_blocks) == 1
    text_block = parsed.content_blocks[0]
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "hello"


def test_assistant_tool_use_message_roundtrip() -> None:
    msg_id = f"msg-{uuid4().hex}"
    tool_id = f"toolu-{uuid4().hex}"
    msg = make_assistant_message(
        msg_id,
        [
            make_text_block("Writing file."),
            make_tool_use_block(tool_id, "Write", {"file_path": "test.txt", "content": "hi"}),
        ],
    )
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "assistant"
    assert isinstance(parsed, ParsedAssistantResponse)
    assert len(parsed.content_blocks) == 2
    assert isinstance(parsed.content_blocks[0], TextBlock)
    tool_block = parsed.content_blocks[1]
    assert isinstance(tool_block, ToolUseBlock)
    assert tool_block.name == "Write"
    assert tool_block.id == tool_id


def test_tool_result_message_roundtrip() -> None:
    tool_id = f"toolu-{uuid4().hex}"
    msg = make_tool_result_message(tool_id, "File written.")
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "user"
    assert isinstance(parsed, ParsedToolResultResponseSimple)
    assert len(parsed.content_blocks) == 1
    assert parsed.content_blocks[0].tool_use_id == tool_id


def test_end_message_roundtrip() -> None:
    session_id = f"test-{uuid4().hex}"
    msg = make_end_message(session_id)
    result = parse_claude_code_json_lines_simple(json.dumps(msg))
    assert result is not None
    msg_type, parsed = result
    assert msg_type == "result"
    assert isinstance(parsed, ParsedEndResponse)
    assert parsed.is_error is False


def test_parse_default_command() -> None:
    command, args = _parse_prompt("Hello, help me with code")
    assert command is None
    assert args == {}


def test_parse_text_command() -> None:
    command, args = _parse_prompt('fake_claude:text `{"text": "hello"}`')
    assert command == "text"
    assert args == {"text": "hello"}


def test_parse_command_without_args() -> None:
    command, args = _parse_prompt("fake_claude:text")
    assert command == "text"
    assert args == {}


def test_parse_unknown_command() -> None:
    command, args = _parse_prompt("fake_claude:nonexistent")
    assert command == "nonexistent"
    assert args == {}


def test_handle_default() -> None:
    messages = handle_default(emit_streaming=False)
    assert len(messages) == 1
    msg = messages[0]
    assert msg["type"] == "assistant"
    text_content = msg["message"]["content"][0]
    assert text_content["text"] == "[FakeClaude] Task completed."


def test_handle_text() -> None:
    messages = handle_text(args={"text": "Hello world"}, emit_streaming=False)
    assert len(messages) == 1
    msg = messages[0]
    assert msg["type"] == "assistant"
    text_content = msg["message"]["content"][0]
    assert text_content["text"] == "Hello world"


def test_handle_stream_text_without_streaming() -> None:
    """Without streaming, stream_text behaves like text — returns only the assistant message."""
    messages = handle_stream_text(args={"text": "Hello streamed"}, emit_streaming=False)
    assert len(messages) == 1
    msg = messages[0]
    assert msg["type"] == "assistant"
    assert msg["message"]["content"][0]["text"] == "Hello streamed"


def test_handle_stream_text_with_streaming(capsys: pytest.CaptureFixture[str]) -> None:
    """With streaming, stream_text writes events to stdout incrementally."""
    messages = handle_stream_text(
        args={"text": "ABCDE", "chunk_size": 2, "delay_seconds": 0},
        emit_streaming=True,
    )

    # The handler returns only the final assistant message
    assert len(messages) == 1
    assert messages[0]["type"] == "assistant"
    assert messages[0]["message"]["content"][0]["text"] == "ABCDE"

    # Streaming events were written directly to stdout
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    events = [json.loads(line) for line in lines]

    # Expect: message_start, content_block_start, 3 deltas (AB, CD, E),
    # content_block_stop, message_stop = 7 events
    assert len(events) == 7
    assert events[0]["event"]["type"] == "message_start"
    assert events[1]["event"]["type"] == "content_block_start"

    # 3 delta events with chunks "AB", "CD", "E"
    deltas = [e for e in events if e["event"]["type"] == "content_block_delta"]
    assert len(deltas) == 3
    assert deltas[0]["event"]["delta"]["text"] == "AB"
    assert deltas[1]["event"]["delta"]["text"] == "CD"
    assert deltas[2]["event"]["delta"]["text"] == "E"

    assert events[5]["event"]["type"] == "content_block_stop"
    assert events[6]["event"]["type"] == "message_stop"


def test_handle_write_file(tmp_path: Path) -> None:
    file_name = f"test_{uuid4().hex}.txt"
    messages = handle_write_file(
        args={"file_path": file_name, "content": "file content"},
        cwd=str(tmp_path),
        emit_streaming=False,
    )
    assert (tmp_path / file_name).read_text() == "file content"
    assert len(messages) == 2
    assert messages[0]["type"] == "assistant"
    assert messages[1]["type"] == "user"

    # Verify tool use block
    tool_use = messages[0]["message"]["content"][1]
    assert tool_use["name"] == "Write"

    # Verify tool result
    tool_result = messages[1]["message"]["content"][0]
    assert tool_result["content"] == "File written successfully."


def test_handle_edit_file(tmp_path: Path) -> None:
    file_name = f"test_{uuid4().hex}.txt"
    (tmp_path / file_name).write_text("Hello world")

    messages = handle_edit_file(
        args={"file_path": file_name, "old_string": "world", "new_string": "earth"},
        cwd=str(tmp_path),
        emit_streaming=False,
    )
    assert (tmp_path / file_name).read_text() == "Hello earth"
    assert len(messages) == 2
    assert messages[0]["type"] == "assistant"

    tool_result = messages[1]["message"]["content"][0]
    assert tool_result["content"] == "File edited successfully."
    assert tool_result["is_error"] is False


def test_handle_edit_file_not_found(tmp_path: Path) -> None:
    file_name = f"test_{uuid4().hex}.txt"
    (tmp_path / file_name).write_text("Hello world")

    messages = handle_edit_file(
        args={"file_path": file_name, "old_string": "nonexistent", "new_string": "replaced"},
        cwd=str(tmp_path),
        emit_streaming=False,
    )
    assert (tmp_path / file_name).read_text() == "Hello world"
    tool_result = messages[1]["message"]["content"][0]
    assert tool_result["is_error"] is True


def test_handle_bash(tmp_path: Path) -> None:
    messages = handle_bash(
        args={"command": "echo hello"},
        cwd=str(tmp_path),
        emit_streaming=False,
    )
    assert len(messages) == 2
    tool_result = messages[1]["message"]["content"][0]
    assert "hello" in tool_result["content"]
    assert tool_result["is_error"] is False


def test_handle_wait_for_file_returns_when_file_exists(tmp_path: Path) -> None:
    """Handler returns immediately when the sentinel file is already present."""
    sentinel = tmp_path / "release.signal"
    sentinel.touch()
    messages = handle_wait_for_file(args={"path": str(sentinel)}, emit_streaming=False)
    assert messages == []


@pytest.fixture
def task_tools_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pin Path.home() to a tmp dir and seed the FakeClaude session id."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    session_id = f"test-{uuid4().hex}"
    make_init_message(session_id)
    return tmp_path / ".claude" / "tasks" / session_id


def test_handle_task_create_writes_file_and_emits_blocks(task_tools_home: Path) -> None:
    args = {
        "id": "1",
        "subject": "Read the file",
        "description": "Read foo.txt and summarise",
        "activeForm": "Reading file",
        "status": "pending",
        "blocks": ["2"],
        "blockedBy": [],
    }
    messages = handle_task_create(args=args, emit_streaming=False)
    assert len(messages) == 2

    task_file = task_tools_home / "1.json"
    assert task_file.exists()
    data = json.loads(task_file.read_text())
    assert data["id"] == "1"
    assert data["subject"] == "Read the file"
    assert data["description"] == "Read foo.txt and summarise"
    assert data["activeForm"] == "Reading file"
    assert data["status"] == "pending"
    assert data["blocks"] == ["2"]
    assert data["blockedBy"] == []
    assert data["owner"] is None
    assert data["metadata"] == {}

    tool_use = messages[0]["message"]["content"][1]
    assert tool_use["name"] == "TaskCreate"
    assert tool_use["input"]["id"] == "1"
    assert tool_use["input"]["subject"] == "Read the file"

    tool_result = messages[1]["message"]["content"][0]
    assert tool_result["content"] == "Task created."


def test_handle_task_create_applies_defaults(task_tools_home: Path) -> None:
    messages = handle_task_create(args={"id": "1", "subject": "Investigate"}, emit_streaming=False)
    assert len(messages) == 2
    data = json.loads((task_tools_home / "1.json").read_text())
    assert data["description"] == ""
    assert data["activeForm"] is None
    assert data["status"] == "pending"
    assert data["blocks"] == []
    assert data["blockedBy"] == []
    assert data["owner"] is None
    assert data["metadata"] == {}


def test_handle_task_update_merges_into_existing_file(task_tools_home: Path) -> None:
    handle_task_create(
        args={"id": "1", "subject": "Investigate", "description": "Original description"},
        emit_streaming=False,
    )
    messages = handle_task_update(args={"id": "1", "status": "in_progress"}, emit_streaming=False)
    assert len(messages) == 2

    data = json.loads((task_tools_home / "1.json").read_text())
    assert data["status"] == "in_progress"
    assert data["subject"] == "Investigate"
    assert data["description"] == "Original description"

    tool_result = messages[1]["message"]["content"][0]
    assert tool_result["content"] == "Task updated."


def test_handle_task_update_creates_file_when_missing(task_tools_home: Path) -> None:
    handle_task_update(
        args={"id": "2", "subject": "New task", "status": "in_progress"},
        emit_streaming=False,
    )
    data = json.loads((task_tools_home / "2.json").read_text())
    assert data["subject"] == "New task"
    assert data["status"] == "in_progress"
    assert data["blocks"] == []
    assert data["blockedBy"] == []


def test_handle_task_update_deletes_file_when_status_is_deleted(task_tools_home: Path) -> None:
    handle_task_create(args={"id": "1", "subject": "Investigate"}, emit_streaming=False)
    task_file = task_tools_home / "1.json"
    assert task_file.exists()

    messages = handle_task_update(args={"id": "1", "status": "deleted"}, emit_streaming=False)
    assert not task_file.exists()

    tool_use = messages[0]["message"]["content"][1]
    assert tool_use["name"] == "TaskUpdate"
    assert tool_use["input"] == {"id": "1", "status": "deleted"}
    tool_result = messages[1]["message"]["content"][0]
    assert tool_result["content"] == "Task updated."


def test_task_lifecycle_create_update_delete_smoke(task_tools_home: Path) -> None:
    handle_task_create(
        args={
            "id": "1",
            "subject": "Subject A",
            "description": "Desc",
            "activeForm": "Doing A",
        },
        emit_streaming=False,
    )
    task_file = task_tools_home / "1.json"
    assert task_file.exists()
    assert json.loads(task_file.read_text())["subject"] == "Subject A"

    handle_task_update(
        args={"id": "1", "status": "in_progress", "blockedBy": ["2"]},
        emit_streaming=False,
    )
    after_update = json.loads(task_file.read_text())
    assert after_update["status"] == "in_progress"
    assert after_update["blockedBy"] == ["2"]
    assert after_update["subject"] == "Subject A"
    assert after_update["description"] == "Desc"
    assert after_update["activeForm"] == "Doing A"

    handle_task_update(args={"id": "1", "status": "deleted"}, emit_streaming=False)
    assert not task_file.exists()


def test_handle_ask_user_question(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """``handle_ask_user_question`` flushes the assistant message, sends the MCP
    ``tools/call`` control_request, blocks on the response, then returns a
    ``user.tool_result`` carrying the response text."""
    questions = [
        {
            "question": "Which option?",
            "header": "Choice",
            "options": [
                {"label": "A", "description": "Option A"},
                {"label": "B", "description": "Option B"},
            ],
            "multiSelect": False,
        }
    ]

    captured_request: dict = {}

    def fake_read(
        expected_request_id: str, tool_use_id: str, timeout_seconds: float, expect_error: bool = False
    ) -> str:
        captured_request["request_id"] = expected_request_id
        captured_request["tool_use_id"] = tool_use_id
        return 'User has answered your questions: "Which option?"="A". You can now continue with the user\'s answers in mind.'

    monkeypatch.setattr(
        "sculptor.agents.testing.fake_claude_commands._read_mcp_control_response_text",
        fake_read,
    )

    messages = handle_ask_user_question(args={"questions": questions}, emit_streaming=False)

    # Inline-flushed: the assistant message went to stdout, the control_request
    # follows it, and only the tool_result remains in the returned list.
    captured_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assistant = next(m for m in captured_lines if m.get("type") == "assistant")
    tool_use = assistant["message"]["content"][1]
    assert tool_use["name"] == "mcp__sculptor__ask_user_question"
    assert tool_use["input"]["questions"] == questions

    control_request = next(m for m in captured_lines if m.get("type") == "control_request")
    assert control_request["request"]["subtype"] == "mcp_message"
    assert control_request["request"]["server_name"] == "sculptor"
    assert control_request["request"]["message"]["method"] == "tools/call"
    assert control_request["request"]["message"]["params"]["name"] == "ask_user_question"
    assert control_request["request"]["message"]["params"]["arguments"] == {"questions": questions}

    assert len(messages) == 2
    tool_result_block = messages[0]["message"]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == tool_use["id"]
    assert tool_result_block["is_error"] is False
    assert "Which option?" in tool_result_block["content"]
    follow_up_assistant = messages[1]
    assert follow_up_assistant["type"] == "assistant"
    follow_up_text = follow_up_assistant["message"]["content"][0]
    assert follow_up_text["type"] == "text"
    assert "[FakeClaude] Task completed." in follow_up_text["text"]
    assert captured_request["tool_use_id"] == tool_use["id"]


def test_handle_multi_step(tmp_path: Path) -> None:
    steps = [
        {"command": "text", "args": {"text": "Step 1"}},
        {"command": "bash", "args": {"command": "echo step2"}},
    ]
    messages = handle_multi_step(
        args={"steps": steps},
        cwd=str(tmp_path),
        emit_streaming=False,
    )

    # text produces 1 message, bash produces 2 (assistant + tool result)
    assert len(messages) == 3
    assert messages[0]["type"] == "assistant"
    assert messages[0]["message"]["content"][0]["text"] == "Step 1"
    assert messages[1]["type"] == "assistant"
    assert messages[2]["type"] == "user"


def test_handle_background_task_started() -> None:
    messages = handle_background_task_started(
        args={"task_id": "bg-1", "description": "Run tests"},
        emit_streaming=False,
    )
    assert len(messages) == 1
    assert messages[0]["type"] == "system"
    assert messages[0]["subtype"] == "task_started"
    assert messages[0]["task_id"] == "bg-1"
    assert messages[0]["description"] == "Run tests"


def test_handle_background_task_notification() -> None:
    messages = handle_background_task_notification(
        args={"task_id": "bg-1", "response_text": "Tests passed."},
        emit_streaming=False,
    )
    # result/success + task_notification + init + assistant = 4
    assert len(messages) == 4
    assert messages[0]["type"] == "result"
    assert messages[0]["subtype"] == "success"
    assert messages[1]["type"] == "system"
    assert messages[1]["subtype"] == "task_notification"
    assert messages[1]["task_id"] == "bg-1"
    assert messages[2]["type"] == "system"
    assert messages[2]["subtype"] == "init"
    assert messages[3]["type"] == "assistant"
    assert messages[3]["message"]["content"][0]["text"] == "Tests passed."


def test_realistic_background_lifecycle_in_multi_step(tmp_path: Path) -> None:
    """Realistic interleaving: task_started mid-turn, notification after result/success."""
    steps = [
        {"command": "text", "args": {"text": "I'll run tests in the background."}},
        {"command": "background_task_started", "args": {"task_id": "bg-1", "description": "Run tests"}},
        {"command": "bash", "args": {"command": "echo main-thread-work"}},
        {"command": "text", "args": {"text": "Main thread done."}},
        {
            "command": "background_task_notification",
            "args": {
                "task_id": "bg-1",
                "response_text": "All 42 tests passed.",
            },
        },
    ]
    messages = handle_multi_step(
        args={"steps": steps},
        cwd=str(tmp_path),
        emit_streaming=False,
    )

    types = [(m.get("type"), m.get("subtype", "")) for m in messages]
    assert types == [
        ("assistant", ""),  # "I'll run tests in the background."
        ("system", "task_started"),  # background task launched (mid-turn)
        ("assistant", ""),  # bash tool call
        ("user", ""),  # bash tool result
        ("assistant", ""),  # "Main thread done."
        ("result", "success"),  # main thread ends
        ("system", "task_notification"),  # background task completed
        ("system", "init"),  # new cycle for background response
        ("assistant", ""),  # "All 42 tests passed."
    ]

    # Verify task_id consistency
    assert messages[1]["task_id"] == "bg-1"
    assert messages[6]["task_id"] == "bg-1"


def test_handle_parallel_tools(tmp_path: Path) -> None:
    tools = [
        {"tool_name": "Bash", "tool_input": {"command": "echo first"}},
        {"tool_name": "Bash", "tool_input": {"command": "echo second"}},
    ]
    messages = handle_parallel_tools(
        args={"tools": tools},
        cwd=str(tmp_path),
        emit_streaming=False,
    )

    # 1 assistant message with 2 tool use blocks + text, then 2 tool results
    assert len(messages) == 3
    assert messages[0]["type"] == "assistant"
    tool_uses = [b for b in messages[0]["message"]["content"] if b.get("type") == "tool_use"]
    assert len(tool_uses) == 2

    assert messages[1]["type"] == "user"
    assert messages[2]["type"] == "user"
    assert "first" in messages[1]["message"]["content"][0]["content"]
    assert "second" in messages[2]["message"]["content"][0]["content"]


def test_generate_id_uniqueness() -> None:
    ids = {generate_id("msg") for _ in range(100)}
    assert len(ids) == 100


def test_generate_id_prefix() -> None:
    msg_id = generate_id("msg")
    assert msg_id.startswith("msg_fakeclaude_")

    tool_id = generate_id("toolu")
    assert tool_id.startswith("toolu_fakeclaude_")


def test_end_to_end_subprocess() -> None:
    """Run fake_claude.py as a subprocess and verify JSONL output."""
    result = subprocess.run(
        [sys.executable, "-m", "sculptor.agents.testing.fake_claude", "-p", "--output-format", "stream-json"],
        input="Hello, help me",
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parents[3]),
    )
    assert result.returncode == 0

    lines = [line for line in result.stdout.strip().split("\n") if line]
    assert len(lines) >= 3

    # First line: init
    first_result = parse_claude_code_json_lines_simple(lines[0])
    assert first_result is not None
    assert first_result[0] == "system"
    assert isinstance(first_result[1], ParsedInitResponse)

    # Last line: end
    last_result = parse_claude_code_json_lines_simple(lines[-1])
    assert last_result is not None
    assert last_result[0] == "result"
    end_response = last_result[1]
    assert isinstance(end_response, ParsedEndResponse)
    assert end_response.is_error is False


def test_end_to_end_unknown_command_exits_with_error() -> None:
    """Unknown fake_claude: commands should exit with code 1."""
    result = subprocess.run(
        [sys.executable, "-m", "sculptor.agents.testing.fake_claude", "-p"],
        input="fake_claude:nonexistent",
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parents[3]),
    )
    assert result.returncode == 1


# --- Multi-turn (borrowing-model) FakeClaude, driven directly over stdin ---
#
# The multi-turn contract is a property of FakeClaude itself, independent of
# whether a caller sends one frame per process or many. These tests assert it
# directly by feeding stdin the way a lingering CLI is fed, rather than routing
# through the process manager.


def _user_frame(content: str) -> str:
    """Build one stream-json user frame line, matching the wrapper's stdin shape."""
    message = {
        "type": "user",
        "session_id": "",
        "message": {"role": "user", "content": content},
        "parent_tool_use_id": None,
    }
    return json.dumps(message) + "\n"


def _run_fake_claude_stream_json(
    stdin_text: str,
    *,
    include_partial: bool = False,
    append_system_prompt: str | None = None,
    replay_user_messages: bool = False,
    home: Path | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run FakeClaude in stream-json input mode, feeding ``stdin_text`` then EOF.

    ``subprocess.run(input=...)`` closes stdin after writing, so this exercises
    the exit-on-EOF path once all frames are consumed. ``home`` pins ``$HOME``
    so a test can inspect (or assert the absence of) the on-disk session file.
    """
    argv = [
        sys.executable,
        "-m",
        "sculptor.agents.testing.fake_claude",
        "-p",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
    ]
    if include_partial:
        argv.append("--include-partial-messages")
    if replay_user_messages:
        argv.append("--replay-user-messages")
    if append_system_prompt is not None:
        argv.extend(["--append-system-prompt", append_system_prompt])
    env = {**os.environ, "HOME": str(home)} if home is not None else None
    return subprocess.run(
        argv,
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parents[3]),
        env=env,
        timeout=timeout,
    )


def _top_level_events(stdout: str) -> list[dict]:
    """Parse stdout JSONL, dropping streaming stream_event lines."""
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    return [e for e in events if e.get("type") != "stream_event"]


@pytest.mark.parametrize("include_partial", [False, True])
def test_stream_json_hosts_multiple_turns_in_one_process(include_partial: bool) -> None:
    """Three user frames on one stdin drive three scripted cycles in one process,
    each bracketed by its own init/result and honoring its own frame's directive."""
    frames = [
        _user_frame('fake_claude:text `{"text": "First turn."}`'),
        _user_frame('fake_claude:text `{"text": "Second turn."}`'),
        _user_frame('fake_claude:text `{"text": "Third turn."}`'),
    ]
    result = _run_fake_claude_stream_json("".join(frames), include_partial=include_partial)
    assert result.returncode == 0, result.stderr

    events = _top_level_events(result.stdout)
    kinds = [(e.get("type"), e.get("subtype", "")) for e in events]
    # Exactly one init → assistant → result bracket per cycle, three cycles.
    assert (
        kinds
        == [
            ("system", "init"),
            ("assistant", ""),
            ("result", "success"),
        ]
        * 3
    )

    # Each cycle honored its own frame's directive, in order.
    assistant_texts = [e["message"]["content"][0]["text"] for e in events if e.get("type") == "assistant"]
    assert assistant_texts == ["First turn.", "Second turn.", "Third turn."]

    # One session per process: every cycle's init reports the same session id.
    init_session_ids = {e["session_id"] for e in events if e.get("subtype") == "init"}
    assert len(init_session_ids) == 1


def test_stream_json_single_frame_then_eof_runs_exactly_one_cycle() -> None:
    """A single frame followed by EOF runs one cycle and nothing more — the loop
    does not synthesize an extra default-handler turn when stdin closes."""
    result = _run_fake_claude_stream_json(_user_frame('fake_claude:text `{"text": "Only turn."}`'))
    assert result.returncode == 0, result.stderr

    events = _top_level_events(result.stdout)
    assert [e.get("subtype") for e in events if e.get("type") == "system"] == ["init"]
    assert len([e for e in events if e.get("type") == "result"]) == 1
    assistant_texts = [e["message"]["content"][0]["text"] for e in events if e.get("type") == "assistant"]
    assert assistant_texts == ["Only turn."]


def test_stream_json_exits_silently_on_immediate_eof() -> None:
    """With no user frame at all, stdin closing makes FakeClaude exit 0 and emit
    nothing, instead of synthesizing a default-handler cycle."""
    result = _run_fake_claude_stream_json("")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_stream_json_immediate_eof_writes_no_session_file(tmp_path: Path) -> None:
    """The silent immediate-EOF exit touches no disk: the session history file
    is deferred until a frame arrives, so a session that emits nothing leaves no
    orphan file. A single real frame under the same pinned HOME does write one,
    proving the negative assertion isn't vacuous."""
    claude_dir = tmp_path / ".claude"

    eof = _run_fake_claude_stream_json("", home=tmp_path)
    assert eof.returncode == 0, eof.stderr
    session_files = list(claude_dir.rglob("*.jsonl")) if claude_dir.exists() else []
    assert session_files == []

    framed = _run_fake_claude_stream_json(_user_frame('fake_claude:text `{"text": "hi"}`'), home=tmp_path)
    assert framed.returncode == 0, framed.stderr
    assert list(claude_dir.rglob("*.jsonl"))


def test_stream_json_system_prompt_directives_run_once_on_first_cycle() -> None:
    """fake_claude: directives in --append-system-prompt run on the first cycle
    only (before that frame's own directives) — an appended system prompt is a
    launch-time input, not a per-turn one — and do not repeat on later cycles."""
    frames = [
        _user_frame('fake_claude:text `{"text": "TURN1"}`'),
        _user_frame('fake_claude:text `{"text": "TURN2"}`'),
    ]
    result = _run_fake_claude_stream_json(
        "".join(frames),
        append_system_prompt='fake_claude:text `{"text": "SYSTEM"}`',
    )
    assert result.returncode == 0, result.stderr

    events = _top_level_events(result.stdout)
    assistant_texts = [e["message"]["content"][0]["text"] for e in events if e.get("type") == "assistant"]
    # SYSTEM runs exactly once, in the first cycle ahead of TURN1; TURN2's cycle has none.
    assert assistant_texts == ["SYSTEM", "TURN1", "TURN2"]


def test_stream_json_interrupt_between_cycles_exits_with_sigterm_code() -> None:
    """An interrupt control_request arriving while idle between cycles tears the
    process down gracefully (SIGTERM exit code) after the completed cycle."""
    interrupt = (
        json.dumps({"type": "control_request", "request_id": "req_x", "request": {"subtype": "interrupt"}}) + "\n"
    )
    result = _run_fake_claude_stream_json(_user_frame('fake_claude:text `{"text": "One turn."}`') + interrupt)
    assert result.returncode == AGENT_EXIT_CODE_FROM_SIGTERM, result.stderr

    events = _top_level_events(result.stdout)
    # The first cycle completed before the interrupt was read; no second cycle began.
    assert len([e for e in events if e.get("subtype") == "init"]) == 1
    assert len([e for e in events if e.get("type") == "result"]) == 1


def _feed_stdin_pipe(payload: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``sys.stdin`` at a real pipe carrying ``payload`` then EOF.

    The unified stdin router reads the raw fd (``sys.stdin.fileno()``), so the
    between-cycle reader tests need a genuine file descriptor rather than an
    ``io.StringIO`` (which has no fileno). Closing the write end after the
    payload gives the reader a clean EOF.
    """
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload.encode("utf-8"))
    os.close(write_fd)
    fake_stdin = os.fdopen(read_fd, "r")
    monkeypatch.setattr(sys, "stdin", fake_stdin)


def test_read_prompt_returns_none_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF (empty stdin) yields None so the caller exits instead of running the
    default handler for a turn the user never sent."""
    _feed_stdin_pipe("", monkeypatch)
    assert _read_prompt_from_stream_json_stdin() is None


def test_read_prompt_returns_empty_string_for_empty_content_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit empty-content user frame is distinct from EOF: it returns ""
    so the default handler still runs for a genuinely empty prompt."""
    frame = json.dumps({"type": "user", "message": {"role": "user", "content": ""}}) + "\n"
    _feed_stdin_pipe(frame, monkeypatch)
    assert _read_prompt_from_stream_json_stdin() == ""


def test_read_prompt_returns_content_for_user_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = json.dumps({"type": "user", "message": {"role": "user", "content": "hello there"}}) + "\n"
    _feed_stdin_pipe(frame, monkeypatch)
    assert _read_prompt_from_stream_json_stdin() == "hello there"


def test_read_prompt_skips_non_user_frames_until_user_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-user frames (control responses, context-usage requests) are ignored
    while scanning for the next user frame."""
    lines = (
        json.dumps({"type": "control_response", "response": {"request_id": "ctx_1"}})
        + "\n"
        + json.dumps({"type": "control_request", "request_id": "c", "request": {"subtype": "get_context_usage"}})
        + "\n"
        + json.dumps({"type": "user", "message": {"role": "user", "content": "actual prompt"}})
        + "\n"
    )
    _feed_stdin_pipe(lines, monkeypatch)
    assert _read_prompt_from_stream_json_stdin() == "actual prompt"


def test_read_prompt_exits_on_idle_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """An interrupt control_request read between cycles exits with the SIGTERM code."""
    frame = json.dumps({"type": "control_request", "request_id": "r", "request": {"subtype": "interrupt"}}) + "\n"
    _feed_stdin_pipe(frame, monkeypatch)
    with pytest.raises(SystemExit) as exc_info:
        _read_prompt_from_stream_json_stdin()
    assert exc_info.value.code == AGENT_EXIT_CODE_FROM_SIGTERM


def test_determinism_same_output_for_same_input() -> None:
    """Same command + args should produce structurally identical output (modulo IDs)."""
    args = {"text": "deterministic test"}

    messages_1 = handle_text(args=args, emit_streaming=False)
    messages_2 = handle_text(args=args, emit_streaming=False)

    # Both should have the same structure
    assert len(messages_1) == len(messages_2)
    assert messages_1[0]["type"] == messages_2[0]["type"]
    assert messages_1[0]["message"]["content"][0]["text"] == messages_2[0]["message"]["content"][0]["text"]


def test_handle_text_with_streaming() -> None:
    messages = handle_text(args={"text": "streamed"}, emit_streaming=True)

    # Should have streaming events before the assistant message
    assert len(messages) > 1
    stream_events = [m for m in messages if m.get("type") == "stream_event"]
    assert len(stream_events) > 0

    # Last message should be the assistant message
    assert messages[-1]["type"] == "assistant"
    assert messages[-1]["message"]["content"][0]["text"] == "streamed"


def test_handle_write_file_with_streaming(tmp_path: Path) -> None:
    file_name = f"test_{uuid4().hex}.txt"
    messages = handle_write_file(
        args={"file_path": file_name, "content": "content"},
        cwd=str(tmp_path),
        emit_streaming=True,
    )
    stream_events = [m for m in messages if m.get("type") == "stream_event"]
    assert len(stream_events) > 0


@pytest.mark.parametrize("emit_streaming", [True, False])
def test_handler_output_roundtrips_through_parser(emit_streaming: bool) -> None:
    """All non-streaming messages from handle_default should parse correctly."""
    messages = handle_default(emit_streaming=emit_streaming)
    for msg in messages:
        if msg.get("type") == "stream_event":
            continue
        result = parse_claude_code_json_lines_simple(json.dumps(msg))
        assert result is not None


def test_read_mcp_control_response_surfaces_response_after_buffered_control_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for SCU-783.

    Sculptor writes ``get_context_usage`` (sent on init) and the MCP
    ``control_response`` back-to-back to FakeClaude's stdin. When both lines
    land on the OS pipe before the helper's first read, ``sys.stdin.readline``
    pulls both into Python's ``BufferedReader`` buffer in one ``read1``,
    returns only the first, and leaves the matching response in Python's
    buffer where ``select.select`` on stdin's fd cannot see it — the helper
    then spins until its 180s MCP timeout and the agent's status pill stays
    visible long past the test's 30s wait. The helper must read the raw fd
    so the response surfaces no matter how the writes batch on the pipe.
    """
    r_fd, w_fd = os.pipe()
    expected_request_id = "mcp_req_scu783"
    irrelevant = {
        "type": "control_request",
        "request_id": "ctx_1",
        "request": {"subtype": "get_context_usage"},
    }
    response = {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": expected_request_id,
            "response": {
                "mcp_response": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32602, "message": "Invalid params"},
                }
            },
        },
    }
    payload = (json.dumps(irrelevant) + "\n" + json.dumps(response) + "\n").encode("utf-8")
    os.write(w_fd, payload)
    # Keep the write end open so select.select does not trip on EOF and
    # mask the buffered-line race — Sculptor never closes stdin between the
    # two writes in production.

    fake_stdin = os.fdopen(r_fd, "r")
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    try:
        result = _read_mcp_control_response_text(
            expected_request_id=expected_request_id,
            tool_use_id="toolu_test",
            timeout_seconds=1.0,
            expect_error=True,
        )
    finally:
        fake_stdin.close()
        os.close(w_fd)

    assert result == "MCP error -32602: Invalid params"


# --- Mid-turn absorption + --replay-user-messages (SCU-1679) ---
#
# The real CLI absorbs a user frame that lands while a turn is in flight as a
# ``queued_command`` attachment (steering), distinct from a between-turns frame
# which starts a plain new turn. FakeClaude reproduces both, keyed on whether
# the frame arrives while a cycle is held open. The transcript shape is checked
# with the same detectors the real-CLI delivery-matrix canary uses.

# A cycle held open on a 1s sleep (long enough for the router to absorb a
# buffered frame during the hold), then a directive that quotes what it absorbed.
_HELD_THEN_REFERENCE_STEPS = [
    {"command": "sleep", "args": {"seconds": 1.0}},
    {"command": "reference_absorbed", "args": {}},
]


def _held_then_reference_frame() -> str:
    """A frame whose cycle holds open, absorbs a buffered frame, then references it."""
    return _user_frame("fake_claude:multi_step `" + json.dumps({"steps": _HELD_THEN_REFERENCE_STEPS}) + "`")


def _read_transcript_from_home(home: Path) -> list[dict]:
    """Parse every JSONL transcript FakeClaude wrote under a pinned ``$HOME``.

    One session runs per process, so this is the single session file; parsing
    all of them keeps the helper robust to the slugged projects path.
    """
    entries: list[dict] = []
    claude_dir = home / ".claude"
    if not claude_dir.exists():
        return entries
    for path in claude_dir.rglob("*.jsonl"):
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _queued_command_prompts(entries: list[dict]) -> list[str]:
    """Prompts of ``queued_command`` attachment entries (the steering shape)."""
    prompts = []
    for entry in entries:
        attachment = entry.get("attachment")
        if (
            entry.get("type") == "attachment"
            and isinstance(attachment, dict)
            and attachment.get("type") == "queued_command"
        ):
            prompts.append(attachment.get("prompt", ""))
    return prompts


def _plain_user_texts(entries: list[dict]) -> list[str]:
    """Text of ordinary (turn-starting) user messages in the transcript."""
    texts = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        content = entry.get("message", {}).get("content", "")
        if isinstance(content, str):
            texts.append(content)
    return texts


def _string_user_echoes(events: list[dict], needle: str) -> list[str]:
    """Stdout user-frame echoes (string content) containing ``needle``."""
    echoes = []
    for event in events:
        if event.get("type") != "user":
            continue
        content = event.get("message", {}).get("content")
        if isinstance(content, str) and needle in content:
            echoes.append(content)
    return echoes


def test_mid_cycle_frame_absorbed_as_queued_command(tmp_path: Path) -> None:
    """Scenario 1: a frame that lands while a cycle is held open is absorbed.

    The held cycle does NOT start a second turn; it records the frame as a
    ``queued_command`` attachment (not a plain user message) and a scripted
    ``reference_absorbed`` step proves the cycle saw the absorbed content.
    """
    steer = f"STEER-{uuid4().hex}"
    result = _run_fake_claude_stream_json(_held_then_reference_frame() + _user_frame(steer), home=tmp_path)
    assert result.returncode == 0, result.stderr

    events = _top_level_events(result.stdout)
    # Absorbed mid-cycle → exactly one turn, not a second init/result cycle.
    assert len([e for e in events if e.get("type") == "result"]) == 1
    assert len([e for e in events if e.get("subtype") == "init"]) == 1

    # The held cycle referenced the absorbed content in its remaining output.
    assistant_texts = [e["message"]["content"][0]["text"] for e in events if e.get("type") == "assistant"]
    assert any(steer in text for text in assistant_texts), assistant_texts

    # Transcript: absorbed frame = queued_command; the turn-starting frame stays plain.
    entries = _read_transcript_from_home(tmp_path)
    assert _queued_command_prompts(entries) == [steer]
    plain = _plain_user_texts(entries)
    assert steer not in plain
    assert any("multi_step" in text for text in plain), plain


def test_absorbed_frame_not_replayed_on_stdout_without_flag(tmp_path: Path) -> None:
    """Without --replay-user-messages the absorbed frame is recorded but never
    echoed on stdout (matching the canary's negative assertion)."""
    steer = f"STEER-{uuid4().hex}"
    result = _run_fake_claude_stream_json(_held_then_reference_frame() + _user_frame(steer), home=tmp_path)
    assert result.returncode == 0, result.stderr

    assert _string_user_echoes(_top_level_events(result.stdout), steer) == []
    assert _queued_command_prompts(_read_transcript_from_home(tmp_path)) == [steer]


def test_replay_echoes_both_frames_in_position(tmp_path: Path) -> None:
    """Scenario 2: with --replay-user-messages both frames are echoed, the
    discriminator being position — the turn-starting frame just after its init,
    the absorbed (steered) frame inside the open turn before its result."""
    steer = f"STEER-{uuid4().hex}"
    result = _run_fake_claude_stream_json(
        _held_then_reference_frame() + _user_frame(steer),
        replay_user_messages=True,
        home=tmp_path,
    )
    assert result.returncode == 0, result.stderr

    events = _top_level_events(result.stdout)
    assert _string_user_echoes(events, steer) == [steer]

    def is_user_echo(event: dict, needle: str) -> bool:
        content = event.get("message", {}).get("content")
        return event.get("type") == "user" and isinstance(content, str) and needle in content

    init_index = next(i for i, e in enumerate(events) if e.get("subtype") == "init")
    turn_starting_index = next(i for i, e in enumerate(events) if is_user_echo(e, "multi_step"))
    steered_index = next(
        i for i, e in enumerate(events) if e.get("type") == "user" and e.get("message", {}).get("content") == steer
    )
    result_index = next(i for i, e in enumerate(events) if e.get("type") == "result")

    # init -> turn-starting echo -> steered echo (inside the open turn) -> result.
    assert init_index < turn_starting_index < steered_index < result_index


def test_between_turns_frames_recorded_as_plain_user(tmp_path: Path) -> None:
    """A between-turns frame is turn-starting, not steering: two fast cycles
    each record a plain user message and zero queued_command attachments."""
    frames = _user_frame('fake_claude:text `{"text": "TURN1"}`') + _user_frame('fake_claude:text `{"text": "TURN2"}`')
    result = _run_fake_claude_stream_json(frames, home=tmp_path)
    assert result.returncode == 0, result.stderr
    assert len([e for e in _top_level_events(result.stdout) if e.get("type") == "result"]) == 2

    entries = _read_transcript_from_home(tmp_path)
    assert _queued_command_prompts(entries) == []
    plain = _plain_user_texts(entries)
    assert any("TURN1" in text for text in plain)
    assert any("TURN2" in text for text in plain)


def test_queued_command_attachment_shape_matches_real_cli() -> None:
    """The absorbed-frame transcript entry carries the real CLI's attachment
    shape, including ``commandMode: "prompt"`` (a queued plain prompt)."""
    entry = make_queued_command_attachment_entry("sess-1", "hello")
    assert entry["type"] == "attachment"
    assert entry["sessionId"] == "sess-1"
    assert entry["attachment"] == {"type": "queued_command", "prompt": "hello", "commandMode": "prompt"}


def test_stdin_router_flushes_final_frame_without_trailing_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    """A last frame written without a trailing newline before EOF is still
    returned (parity with the old ``for line in sys.stdin`` iterator), not
    dropped — it is flushed once EOF is observed, then EOF is reported.

    Data and EOF arrive in separate pipe reads, so the frame surfaces across
    the loop iterations every real caller already runs (they retry on
    ``_STDIN_TIMEOUT``).
    """
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b'{"type": "user", "message": {"role": "user", "content": "tail"}}')  # no newline
    os.close(write_fd)
    fake_stdin = os.fdopen(read_fd, "r")
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    try:
        frame: object = None
        for _ in range(5):
            frame = _STDIN_ROUTER.next_frame(timeout=1.0)
            if isinstance(frame, dict):
                break
        assert isinstance(frame, dict), frame
        assert frame["message"]["content"] == "tail"
        assert _STDIN_ROUTER.next_frame(timeout=1.0) is _STDIN_EOF
    finally:
        fake_stdin.close()


def test_mcp_reader_absorbs_user_frame_while_awaiting_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The unified reader routes each frame by type in one pass: a user frame
    arriving while a handler awaits its MCP control_response is absorbed
    (recorded as queued_command), while the awaited response is still delivered.

    This is the core of the reader unification — previously the MCP reader
    discarded any non-matching line, silently losing a mid-wait user frame.
    """
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    session_id = f"session-{uuid4().hex}"
    make_init_message(session_id)  # sets get_last_session_id() for the transcript write
    configure_stdin_router(replay_user_messages=False, persist_session=True)

    steer = f"STEER-{uuid4().hex}"
    request_id = "mcp_req_absorb"
    user_frame = json.dumps({"type": "user", "message": {"role": "user", "content": steer}})
    response = json.dumps(
        {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": {"mcp_response": {"result": {"content": [{"type": "text", "text": "ANSWER"}]}}},
            },
        }
    )
    read_fd, write_fd = os.pipe()
    # User frame arrives first, then the awaited response — the reader must serve both.
    os.write(write_fd, (user_frame + "\n" + response + "\n").encode("utf-8"))
    os.close(write_fd)
    fake_stdin = os.fdopen(read_fd, "r")
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    try:
        results = _read_mcp_control_responses({request_id}, timeout_seconds=2.0)
    finally:
        fake_stdin.close()

    assert results[request_id]["result"]["content"][0]["text"] == "ANSWER"
    assert _ABSORBED_FRAMES == [steer]
    assert _queued_command_prompts(_read_transcript_from_home(tmp_path)) == [steer]


class _BackgroundLineReader:
    """Collects a subprocess's stdout JSONL on a daemon thread, so a test can
    interleave stdin writes with waits on observed events (true mid-cycle
    timing, unlike ``subprocess.run`` which writes all of stdin up front)."""

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        for raw_line in self._stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self._lock:
                self._events.append(obj)

    def events(self) -> list[dict]:
        with self._lock:
            return list(self._events)

    def count(self, predicate: Callable[[dict], bool]) -> int:
        return sum(1 for e in self.events() if predicate(e))

    def wait_for(self, predicate: Callable[[dict], bool], timeout: float, description: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(predicate(e) for e in self.events()):
                return
            time.sleep(0.02)
        raise AssertionError(f"Timed out waiting for {description}; events={self.events()}")


def test_mid_cycle_absorption_true_timing_via_wait_for_file(tmp_path: Path) -> None:
    """Scenario 1 with genuine mid-cycle timing: the steer frame is written only
    AFTER the held cycle is observed in flight (not pre-buffered), then absorbed."""
    steer = f"STEER-{uuid4().hex}"
    sentinel = tmp_path / "release.signal"
    argv = [
        sys.executable,
        "-m",
        "sculptor.agents.testing.fake_claude",
        "-p",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
        "--replay-user-messages",
    ]
    env = {**os.environ, "HOME": str(tmp_path)}
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(Path(__file__).parents[3]),
        env=env,
    )
    assert process.stdin is not None and process.stdout is not None
    reader = _BackgroundLineReader(process.stdout)
    try:
        # Hold a cycle open on the sentinel, then wait until it is genuinely in flight.
        process.stdin.write(_user_frame("fake_claude:wait_for_file `" + json.dumps({"path": str(sentinel)}) + "`"))
        process.stdin.flush()
        reader.wait_for(lambda e: e.get("subtype") == "init", timeout=15, description="system/init")

        # Inject the steer frame mid-cycle; its echo proves the held cycle absorbed it.
        process.stdin.write(_user_frame(steer))
        process.stdin.flush()
        reader.wait_for(
            lambda e: e.get("type") == "user" and e.get("message", {}).get("content") == steer,
            timeout=15,
            description="steered replay echo",
        )
        # Absorption must not have opened a second turn.
        assert reader.count(lambda e: e.get("type") == "result") == 0

        sentinel.touch()  # release the held cycle so it finishes naturally
        process.stdin.close()
        assert process.wait(timeout=15) == 0, process.stderr.read() if process.stderr else ""
    finally:
        if process.poll() is None:
            process.kill()
        if process.stderr is not None:
            process.stderr.close()
        process.stdout.close()

    assert reader.count(lambda e: e.get("type") == "result") == 1
    assert _queued_command_prompts(_read_transcript_from_home(tmp_path)) == [steer]
