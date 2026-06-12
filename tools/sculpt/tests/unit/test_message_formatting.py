"""Unit tests for the message formatting module."""

from sculpt.message_formatting import format_content_block
from sculpt.message_formatting import format_message


def test_text_block() -> None:
    result = format_content_block({"type": "text", "text": "Hello\nworld"})
    assert result == "Hello\nworld"


def test_tool_use_read() -> None:
    block = {"type": "tool_use", "name": "Read", "id": "x", "input": {"file_path": "src/main.py"}}
    assert format_content_block(block) == "[Read] src/main.py"


def test_tool_use_edit() -> None:
    block = {"type": "tool_use", "name": "Edit", "id": "x", "input": {"file_path": "src/main.py"}}
    assert format_content_block(block) == "[Edit] src/main.py"


def test_tool_use_write() -> None:
    block = {"type": "tool_use", "name": "Write", "id": "x", "input": {"file_path": "out.txt"}}
    assert format_content_block(block) == "[Write] out.txt"


def test_tool_use_grep() -> None:
    block = {"type": "tool_use", "name": "Grep", "id": "x", "input": {"pattern": "TODO"}}
    assert format_content_block(block) == '[Grep] "TODO"'


def test_tool_use_glob() -> None:
    block = {"type": "tool_use", "name": "Glob", "id": "x", "input": {"pattern": "**/*.py"}}
    assert format_content_block(block) == "[Glob] **/*.py"


def test_tool_use_bash() -> None:
    block = {"type": "tool_use", "name": "Bash", "id": "x", "input": {"command": "ls -la"}}
    assert format_content_block(block) == "[Bash] ls -la"


def test_tool_use_bash_truncation() -> None:
    long_cmd = "a" * 100
    block = {"type": "tool_use", "name": "Bash", "id": "x", "input": {"command": long_cmd}}
    result = format_content_block(block)
    assert result is not None
    assert len(result) <= len("[Bash] ") + 60
    assert result.endswith("...")


def test_tool_use_agent() -> None:
    block = {"type": "tool_use", "name": "Agent", "id": "x", "input": {"description": "Explore codebase"}}
    assert format_content_block(block) == "[Agent] Explore codebase"


def test_tool_use_unknown_tool() -> None:
    block = {"type": "tool_use", "name": "Custom", "id": "x", "input": {}}
    assert format_content_block(block) == "[Custom]"


def test_tool_use_missing_input_field() -> None:
    block = {"type": "tool_use", "name": "Read", "id": "x", "input": {}}
    assert format_content_block(block) == "[Read]"


def test_tool_result_hidden() -> None:
    block = {"type": "tool_result", "toolUseId": "x", "toolName": "Read", "content": {}, "isError": False}
    assert format_content_block(block) is None


def test_tool_result_simple_hidden() -> None:
    block = {"type": "tool_result_simple", "toolUseId": "x", "toolName": "Read", "content": {}, "isError": False}
    assert format_content_block(block) is None


def test_error_block() -> None:
    block = {"type": "error", "message": "File not found", "traceback": "", "errorType": "IOError"}
    assert format_content_block(block) == "[Error] File not found"


def test_warning_block() -> None:
    block = {"type": "warning", "message": "Deprecated", "traceback": "", "warningType": "DeprecationWarning"}
    assert format_content_block(block) == "[Warning] Deprecated"


def test_file_block() -> None:
    block = {"type": "file", "source": "/tmp/out.csv"}
    assert format_content_block(block) == "[File] /tmp/out.csv"


def test_context_summary_block() -> None:
    block = {"type": "context_summary", "text": "Summary of context"}
    assert format_content_block(block) == "[Context Summary] Summary of context"


def test_context_cleared_block() -> None:
    block = {"type": "context_cleared", "text": "Cleared successfully"}
    assert format_content_block(block) == "[Context Cleared]"


def test_resume_response_block() -> None:
    block = {"type": "resume_response"}
    assert format_content_block(block) == "[Resumed]"


def test_unknown_block_type() -> None:
    block = {"type": "unknown_new_type"}
    assert format_content_block(block) is None


def test_format_message_full() -> None:
    message = {
        "role": "assistant",
        "id": "msg_123",
        "approximateCreationTime": "2026-03-20T19:31:00Z",
        "content": [
            {"type": "text", "text": "Let me look at the codebase."},
            {"type": "tool_use", "name": "Read", "id": "tu1", "input": {"file_path": "main.py"}},
            {"type": "tool_result", "toolUseId": "tu1", "toolName": "Read", "content": {}, "isError": False},
            {"type": "text", "text": "This is the Sculptor CLI tool."},
        ],
        "stopped": False,
    }
    result = format_message(message)
    assert "[assistant] 2026-03-20 19:31" in result
    assert "  Let me look at the codebase." in result
    assert "  [Read] main.py" in result
    assert "tool_result" not in result
    assert "  This is the Sculptor CLI tool." in result


def test_format_message_empty_content() -> None:
    message = {
        "role": "user",
        "id": "msg_456",
        "approximateCreationTime": "2026-03-20T19:31:00Z",
        "content": [],
    }
    result = format_message(message)
    assert result == "[user] 2026-03-20 19:31"


def test_format_message_missing_timestamp() -> None:
    message = {
        "role": "user",
        "content": [{"type": "text", "text": "hello"}],
    }
    result = format_message(message)
    assert result.startswith("[user]")
    assert "  hello" in result


def test_format_message_user_text() -> None:
    message = {
        "role": "user",
        "id": "msg_789",
        "approximateCreationTime": "2026-03-20T19:31:00Z",
        "content": [{"type": "text", "text": "what is going on"}],
    }
    result = format_message(message)
    assert "[user] 2026-03-20 19:31" in result
    assert "  what is going on" in result
