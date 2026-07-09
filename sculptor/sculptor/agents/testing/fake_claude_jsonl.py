"""Helper functions for constructing JSONL dicts that mimic claude -p --output-format=stream-json."""

import itertools
import json
import os
from collections.abc import Sequence
from pathlib import Path

from sculptor.agents.default.claude_code_sdk.harness import compute_claude_jsonl_directory

_id_counter = itertools.count(1)

_LAST_SESSION_ID: str | None = None


def generate_id(prefix: str = "msg") -> str:
    """Return a unique ID string like 'msg_fakeclaude_001'."""
    return f"{prefix}_fakeclaude_{next(_id_counter):03d}"


def get_last_session_id() -> str | None:
    """Return the session id from the most recent make_init_message call."""
    return _LAST_SESSION_ID


def session_transcript_path(session_id: str) -> Path:
    """Path of the on-disk session JSONL for ``session_id``.

    Mirrors ``ClaudeCodeHarness.get_jsonl_path``: the CLI is launched with the
    working directory as its CWD, so the transcript lands under the slugged
    projects tree that ``compute_claude_jsonl_directory`` derives from HOME and
    that CWD. Read HOME/CWD at call time so a test that pins ``$HOME`` gets the
    path it expects.
    """
    resolved_cwd = Path(os.path.realpath(os.getcwd()))
    return compute_claude_jsonl_directory(Path.home(), resolved_cwd) / f"{session_id}.jsonl"


def append_transcript_entry(session_id: str, entry: dict) -> None:
    """Append one JSONL entry to ``session_id``'s on-disk transcript.

    Creating the projects directory on first write mirrors the real CLI, which
    materializes the transcript lazily once a turn actually runs — so a session
    that emits nothing (immediate EOF) leaves no file behind.
    """
    path = session_transcript_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as transcript:
        transcript.write(json.dumps(entry) + "\n")


def make_plain_user_transcript_entry(session_id: str, content: str) -> dict:
    """Transcript entry for a turn-starting user frame (a plain user message).

    The top-level ``sessionId`` (camelCase, matching the real CLI's on-disk
    shape) is what ``is_session_id_valid`` scans for, so writing this per turn
    also keeps the session resumable.
    """
    return {
        "type": "user",
        "sessionId": session_id,
        "message": {"role": "user", "content": content},
    }


def make_queued_command_attachment_entry(session_id: str, prompt: str) -> dict:
    """Transcript entry for a frame absorbed mid-cycle (the steering shape).

    The real CLI records a frame that arrives while a turn is in flight as a
    ``queued_command`` attachment rather than a plain user message; this is the
    on-disk marker that distinguishes steering from a turn-starting follow-up.
    """
    return {
        "type": "attachment",
        "sessionId": session_id,
        "attachment": {"type": "queued_command", "prompt": prompt},
    }


def make_user_frame_echo(content: str) -> dict:
    """Stdout echo of an accepted user frame (the ``--replay-user-messages`` shape).

    The real CLI, launched with ``--replay-user-messages``, re-emits each
    accepted frame as a ``type:"user"`` event whose message content is a plain
    string — the same shape the wrapper writes on stdin.
    """
    return {"type": "user", "message": {"role": "user", "content": content}}


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

    ``workflow_progress`` mirrors the real CLI: a delta of
    workflow_phase/workflow_agent entries (camelCase keys) whose state
    changed since the previous payload, omitted entirely on pure token-tick
    batches.
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
    tool_use_id: str | None,
    status: str = "completed",
    summary: str = "",
    duration_ms: int | None = None,
) -> dict:
    """Return a dict for a system/task_notification message.

    When ``duration_ms`` is provided it is emitted nested under ``usage`` to
    match the real Claude CLI shape (see SCU-1151).

    Pass ``tool_use_id=None`` to omit the field entirely. The real CLI drops
    ``tool_use_id`` when a background task is orphaned by a process exit (e.g. a
    restart) and reported as failed on resume, because the launching tool call's
    id was lost with the dead process — see SCU-1666.
    """
    msg: dict = {
        "type": "system",
        "subtype": "task_notification",
        "task_id": task_id,
        "status": status,
        "summary": summary,
    }
    if tool_use_id is not None:
        msg["tool_use_id"] = tool_use_id
    if duration_ms is not None:
        msg["usage"] = {"duration_ms": duration_ms}
    return msg


def make_task_updated_message(
    task_id: str,
    status: str = "completed",
) -> dict:
    """Return a dict for a system/task_updated message.

    The real Claude CLI emits task_updated as a background task moves through
    its lifecycle; the status lives under ``patch``. A terminal ``patch.status``
    (completed/failed/stopped) can arrive with NO accompanying task_notification
    when the task finishes while the CLI is busy with another turn (see the
    handling in ``output_processor._process_output``).
    """
    return {
        "type": "system",
        "subtype": "task_updated",
        "task_id": task_id,
        "patch": {"status": status},
    }


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


def make_end_message(
    session_id: str | None,
    is_error: bool = False,
    result: str = "",
    api_error_status: int | None = None,
) -> dict:
    """Return a dict for the end-of-stream message.

    ``api_error_status`` mirrors the real CLI: the HTTP status is included only when
    the turn failed on an API error, and the key is omitted entirely otherwise.
    """
    message = {
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
    if api_error_status is not None:
        message["api_error_status"] = api_error_status
    return message


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
