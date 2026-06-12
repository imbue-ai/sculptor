"""Content block and message formatters for terminal display."""

import datetime
from collections.abc import Mapping
from typing import Any

from sculpt.formatting import truncate


def _format_tool_use(block: Mapping[str, Any]) -> str:
    """Format a ToolUseBlock as a one-line summary."""
    name = block.get("name", "Unknown")
    tool_input = block.get("input", {})

    if name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "")
        if path:
            return f"[{name}] {path}"
    elif name == "Glob":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f"[{name}] {pattern}"
    elif name == "Grep":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f'[{name}] "{pattern}"'
    elif name == "Bash":
        command = tool_input.get("command", "")
        if command:
            return f"[{name}] {truncate(command, max_length=60)}"
    elif name == "Agent":
        description = tool_input.get("description", "")
        if description:
            return f"[{name}] {description}"

    return f"[{name}]"


def format_content_block(block: Mapping[str, Any]) -> str | None:
    """Format a single content block for terminal display.

    Returns None for blocks that should be hidden (tool results, unknown types).
    """
    block_type = block.get("type", "")

    if block_type == "text":
        return block.get("text", "")
    elif block_type == "tool_use":
        return _format_tool_use(block)
    elif block_type in ("tool_result", "tool_result_simple"):
        return None
    elif block_type == "error":
        return f"[Error] {block.get('message', '')}"
    elif block_type == "warning":
        return f"[Warning] {block.get('message', '')}"
    elif block_type == "file":
        return f"[File] {block.get('source', '')}"
    elif block_type == "context_summary":
        return f"[Context Summary] {block.get('text', '')}"
    elif block_type == "context_cleared":
        return "[Context Cleared]"
    elif block_type == "resume_response":
        return "[Resumed]"
    else:
        return None


def format_message(message: Mapping[str, Any]) -> str:
    """Format a raw ChatMessage dict for terminal display."""
    role = message.get("role", "unknown")

    timestamp_str = message.get("approximateCreationTime", "")
    if timestamp_str:
        try:
            dt = datetime.datetime.fromisoformat(timestamp_str)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            formatted_time = ""
    else:
        formatted_time = ""

    header = f"[{role}] {formatted_time}".rstrip()

    content_blocks = message.get("content", [])
    formatted_parts: list[str] = []
    for block in content_blocks:
        formatted = format_content_block(block)
        if formatted is not None:
            indented = "\n".join(f"  {line}" for line in formatted.split("\n"))
            formatted_parts.append(indented)

    if formatted_parts:
        return header + "\n" + "\n\n".join(formatted_parts)
    return header
