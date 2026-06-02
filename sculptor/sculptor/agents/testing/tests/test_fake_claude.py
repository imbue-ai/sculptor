"""Unit tests for FakeClaude script."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.agents.testing.fake_claude import _parse_prompt
from sculptor.agents.testing.fake_claude_commands import _read_mcp_control_response_text
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
from sculptor.agents.testing.fake_claude_jsonl import make_task_notification_message
from sculptor.agents.testing.fake_claude_jsonl import make_task_started_message
from sculptor.agents.testing.fake_claude_jsonl import make_text_block
from sculptor.agents.testing.fake_claude_jsonl import make_tool_result_message
from sculptor.agents.testing.fake_claude_jsonl import make_tool_use_block
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.claude_state import ParsedAssistantResponse
from sculptor.state.claude_state import ParsedEndResponse
from sculptor.state.claude_state import ParsedInitResponse
from sculptor.state.claude_state import ParsedTaskNotificationResponse
from sculptor.state.claude_state import ParsedTaskStartedResponse
from sculptor.state.claude_state import ParsedToolResultResponseSimple
from sculptor.state.claude_state import parse_claude_code_json_lines_simple

# ========== JSONL Round-Trip Tests ==========


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


# ========== Command Parsing Tests ==========


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


# ========== Command Handler Tests ==========


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


# ========== Generate ID Tests ==========


def test_generate_id_uniqueness() -> None:
    ids = {generate_id("msg") for _ in range(100)}
    assert len(ids) == 100


def test_generate_id_prefix() -> None:
    msg_id = generate_id("msg")
    assert msg_id.startswith("msg_fakeclaude_")

    tool_id = generate_id("toolu")
    assert tool_id.startswith("toolu_fakeclaude_")


# ========== End-to-End Subprocess Test ==========


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


# ========== Determinism Test ==========


def test_determinism_same_output_for_same_input() -> None:
    """Same command + args should produce structurally identical output (modulo IDs)."""
    args = {"text": "deterministic test"}

    messages_1 = handle_text(args=args, emit_streaming=False)
    messages_2 = handle_text(args=args, emit_streaming=False)

    # Both should have the same structure
    assert len(messages_1) == len(messages_2)
    assert messages_1[0]["type"] == messages_2[0]["type"]
    assert messages_1[0]["message"]["content"][0]["text"] == messages_2[0]["message"]["content"][0]["text"]


# ========== Streaming Tests ==========


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


# ========== Handler Roundtrip Tests ==========


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
