"""Helper functions for constructing JSONL dicts that mimic claude -p --output-format=stream-json."""

import itertools
import json
from collections.abc import Sequence

_id_counter = itertools.count(1)

_LAST_SESSION_ID: str | None = None


def generate_id(prefix: str = "msg") -> str:
    """Return a unique ID string like 'msg_fakeclaude_001'."""
    return f"{prefix}_fakeclaude_{next(_id_counter):03d}"


def get_last_session_id() -> str | None:
    """Return the session id from the most recent make_init_message call."""
    return _LAST_SESSION_ID


def make_init_message(session_id: str) -> dict:
    """Return a dict for the init message."""
    global _LAST_SESSION_ID
    _LAST_SESSION_ID = session_id
    return {
        "type": "system",
        "subtype": "init",
        "session_id": session_id,
        "tools": [
            "Bash",
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "TaskCreate",
            "TaskUpdate",
            "TaskList",
            "TaskGet",
            "AskUserQuestion",
        ],
        "mcp_servers": [],
    }


def make_task_started_message(
    task_id: str,
    tool_use_id: str,
    description: str = "",
    task_type: str = "local_bash",
    workflow_name: str | None = None,
) -> dict:
    """Return a dict for a system/task_started message.

    ``workflow_name`` is only present on the wire for Workflow tasks
    (task_type="local_workflow").
    """
    msg: dict = {
        "type": "system",
        "subtype": "task_started",
        "task_id": task_id,
        "tool_use_id": tool_use_id,
        "description": description,
        "task_type": task_type,
    }
    if workflow_name is not None:
        msg["workflow_name"] = workflow_name
    return msg


def make_task_progress_message(
    task_id: str,
    tool_use_id: str,
    description: str = "",
    total_tokens: int = 0,
    tool_uses: int = 0,
    duration_ms: int = 0,
    last_tool_name: str | None = None,
    workflow_progress: list[dict] | None = None,
) -> dict:
    """Return a dict for a system/task_progress message.

    ``workflow_progress`` mirrors the real CLI: present (a full snapshot of
    workflow_phase/workflow_agent entries, camelCase keys) when the tree
    changed, and omitted entirely on pure token-tick batches.
    """
    msg: dict = {
        "type": "system",
        "subtype": "task_progress",
        "task_id": task_id,
        "tool_use_id": tool_use_id,
        "description": description,
        "usage": {"total_tokens": total_tokens, "tool_uses": tool_uses, "duration_ms": duration_ms},
    }
    if last_tool_name is not None:
        msg["last_tool_name"] = last_tool_name
    if workflow_progress is not None:
        msg["workflow_progress"] = workflow_progress
    return msg


def make_workflow_phase_entry(index: int, title: str, kind: str = "") -> dict:
    """Return a workflow_phase entry for a workflow_progress tree."""
    return {"type": "workflow_phase", "index": index, "title": title, "kind": kind}


def make_workflow_agent_entry(
    index: int,
    label: str,
    phase_index: int = 0,
    phase_title: str = "",
    state: str = "start",
    model: str = "fake-claude",
    tokens: int | None = None,
    tool_calls: int | None = None,
    duration_ms: int | None = None,
    last_tool_summary: str | None = None,
    result_preview: str | None = None,
    error: str | None = None,
    prompt_preview: str = "",
) -> dict:
    """Return a workflow_agent entry for a workflow_progress tree (camelCase wire keys)."""
    entry: dict = {
        "type": "workflow_agent",
        "index": index,
        "label": label,
        "phaseIndex": phase_index,
        "phaseTitle": phase_title,
        "state": state,
        "model": model,
        "promptPreview": prompt_preview,
    }
    if tokens is not None:
        entry["tokens"] = tokens
    if tool_calls is not None:
        entry["toolCalls"] = tool_calls
    if duration_ms is not None:
        entry["durationMs"] = duration_ms
    if last_tool_summary is not None:
        entry["lastToolSummary"] = last_tool_summary
    if result_preview is not None:
        entry["resultPreview"] = result_preview
    if error is not None:
        entry["error"] = error
    return entry


def make_task_notification_message(
    task_id: str,
    tool_use_id: str,
    status: str = "completed",
    summary: str = "",
    duration_ms: int | None = None,
) -> dict:
    """Return a dict for a system/task_notification message.

    When ``duration_ms`` is provided it is emitted nested under ``usage`` to
    match the real Claude CLI shape (see SCU-1151).
    """
    msg: dict = {
        "type": "system",
        "subtype": "task_notification",
        "task_id": task_id,
        "tool_use_id": tool_use_id,
        "status": status,
        "summary": summary,
    }
    if duration_ms is not None:
        msg["usage"] = {"duration_ms": duration_ms}
    return msg


def make_text_block(text: str) -> dict:
    """Return a text content block."""
    return {"type": "text", "text": text}


def make_tool_use_block(tool_id: str, tool_name: str, tool_input: dict) -> dict:
    """Return a tool_use content block."""
    return {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input}


def make_assistant_message(
    message_id: str,
    content_blocks: Sequence[dict],
    parent_tool_use_id: str | None = None,
) -> dict:
    """Return a dict for an assistant message."""
    has_tool_use = any(block.get("type") == "tool_use" for block in content_blocks)
    stop_reason = None if has_tool_use else "end_turn"

    result: dict = {
        "type": "assistant",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": "fake-claude",
            "content": list(content_blocks),
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    }
    if parent_tool_use_id is not None:
        result["parent_tool_use_id"] = parent_tool_use_id
    return result


def make_tool_result_message(
    tool_use_id: str,
    content: str,
    is_error: bool = False,
    parent_tool_use_id: str | None = None,
) -> dict:
    """Return a dict for a tool result message."""
    result: dict = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
        "parent_tool_use_id": parent_tool_use_id,
    }
    return result


def make_compact_summary_user_message(summary_text: str, session_id: str = "") -> dict:
    """Return a synthetic user message containing the compaction summary.

    Matches the real CLI's post-compaction output: a ``user`` message with
    ``isSynthetic: true`` whose content is the compacted conversation summary.
    """
    return {
        "type": "user",
        "isSynthetic": True,
        "session_id": session_id,
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": summary_text}],
        },
    }


def make_compact_status_message(session_id: str = "") -> dict:
    """Return a ``system/status`` message indicating compaction succeeded.

    The real CLI emits this immediately after compaction completes, before the
    summary user message.
    """
    return {
        "type": "system",
        "subtype": "status",
        "status": None,
        "compact_result": "success",
        "session_id": session_id,
    }


def make_compact_boundary_message(session_id: str = "") -> dict:
    """Return a ``system/compact_boundary`` message with compaction metadata.

    Emitted by the real CLI between the status message and the summary.
    """
    return {
        "type": "system",
        "subtype": "compact_boundary",
        "session_id": session_id,
        "compact_metadata": {
            "trigger": "auto",
            "pre_tokens": 50000,
            "post_tokens": 5000,
            "duration_ms": 10000,
        },
    }


def make_hook_callback_control_request(
    request_id: str,
    callback_id: str,
    hook_input: dict,
) -> dict:
    """Return a ``control_request`` for a hook callback (emitted on stdout)."""
    return {
        "type": "control_request",
        "request_id": request_id,
        "request": {
            "subtype": "hook_callback",
            "callback_id": callback_id,
            "input": hook_input,
        },
    }


def make_end_message(session_id: str | None, is_error: bool = False, result: str = "") -> dict:
    """Return a dict for the end-of-stream message."""
    return {
        "type": "result",
        "subtype": "success",
        "is_error": is_error,
        "result": result,
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
        "total_cost_usd": 0,
    }


def make_streaming_text_events(
    message_id: str,
    text: str,
    parent_tool_use_id: str | None = None,
) -> list[dict]:
    """Return stream event dicts for a complete text response streaming sequence."""
    events: list[dict] = []

    # message_start
    message_start: dict = {
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
        "parent_tool_use_id": parent_tool_use_id,
    }
    events.append(message_start)

    # content_block_start for text at index 0
    events.append(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        }
    )

    # content_block_delta with the full text
    events.append(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        }
    )

    # content_block_stop
    events.append(
        {
            "type": "stream_event",
            "event": {"type": "content_block_stop", "index": 0},
        }
    )

    # message_stop
    events.append(
        {
            "type": "stream_event",
            "event": {"type": "message_stop"},
        }
    )

    return events


def make_streaming_tool_events(
    message_id: str,
    tool_blocks: Sequence[dict],
    text_prefix: str = "",
    parent_tool_use_id: str | None = None,
) -> list[dict]:
    """Return stream events for an assistant message with optional text prefix + tool use blocks."""

    events: list[dict] = []

    # message_start
    message_start: dict = {
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
        "parent_tool_use_id": parent_tool_use_id,
    }
    events.append(message_start)

    index = 0

    # Text block at index 0
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
    if text_prefix:
        events.append(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": text_prefix},
                },
            }
        )
    events.append(
        {
            "type": "stream_event",
            "event": {"type": "content_block_stop", "index": index},
        }
    )
    index += 1

    # Tool blocks at subsequent indices
    for tool_block in tool_blocks:
        events.append(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_block["id"],
                        "name": tool_block["name"],
                        "input": {},
                    },
                },
            }
        )

        tool_input_json = json.dumps(tool_block["input"])
        events.append(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": tool_input_json},
                },
            }
        )

        events.append(
            {
                "type": "stream_event",
                "event": {"type": "content_block_stop", "index": index},
            }
        )
        index += 1

    # message_stop
    events.append(
        {
            "type": "stream_event",
            "event": {"type": "message_stop"},
        }
    )

    return events


def make_streaming_interleaved_events(
    message_id: str,
    blocks: Sequence[dict],
    parent_tool_use_id: str | None = None,
) -> list[dict]:
    """Emit stream events for an assistant message with arbitrary ordered text
    and tool_use blocks at sequential streaming indices.

    Unlike ``make_streaming_tool_events``, this helper does not force a text
    block at index 0 and supports zero-delta text blocks (by passing an empty
    text string). Both are shapes the real SDK emits but ``make_streaming_
    tool_events`` does not produce.

    Each entry in ``blocks`` must be one of:
      - ``{"type": "text", "text": <str>}``   (no text_delta emitted if "")
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
            "parent_tool_use_id": parent_tool_use_id,
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

    events.append(
        {
            "type": "stream_event",
            "event": {"type": "message_stop"},
        }
    )

    return events
