"""Parse the Sculptor sub-agent extension's structured lifecycle payloads.

pi-core has no sub-agent protocol surface, so Sculptor ships a pinned extension
(`extensions/sculptor_subagent.ts`) that registers a `subagent` tool. The tool
spawns each child as its own `pi` process and returns IMMEDIATELY (the agent
keeps control; the turn does not block), then reports completion out-of-band.
Two payloads cross the wire, both parsed here:

START — the tool result's `{content, details}` envelope, with the task under
`details.task`:

    {"v": 1, "task": {"taskId", "toolCallId", "label", "pgids": [int, ...],
                      "count": int, "status": "running"}}

COMPLETION — a fire-and-forget `notify` whose `message` string is JSON carrying
the marker key, under which the full per-child snapshot rides:

    {"sculptorSubagentTask": {"v": 1, "taskId", "toolCallId",
        "status": "completed"|"failed",
        "children": [
            {"childId", "label", "task", "status": "running"|"done"|"error",
             "stopReason"?, "exitCode"?,
             "events": [
                 {"seq", "kind": "tool_call",   "toolCallId", "toolName", "args"},
                 {"seq", "kind": "tool_result", "toolCallId", "text", "isError"},
                 {"seq", "kind": "text",        "text"}]}]}}

The adapter (`agent_wrapper`) maps START onto a started indicator (recording the
children's `pgids` so a shutdown can SIGTERM those groups in the environment) and
COMPLETION onto nested, attributed child blocks — a parent `Agent` tool with each
child's own tool calls and text grouped beneath it (`parent_tool_use_id`),
matching Claude's background sub-agent rendering — plus a completion
notification.

Parsing is permissive — these payloads cross a subprocess / extension boundary,
so a malformed value or unknown version yields `None` (the caller then treats the
`subagent` call as an ordinary tool with no sub-agent lifecycle) and a bad event
is skipped.

Wire contract shared with `extensions/sculptor_subagent.ts`: the version, the
marker key, and the field names below MUST match what that extension emits.
Changing one means editing both in the same change.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from sculptor.agents.pi_agent.tool_rendering import map_pi_tool_call
from sculptor.primitives.ids import ToolUseID
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import GenericToolContent
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.claude_state import get_tool_invocation_string

# Payload schema version (the `v` field); a payload with a different `v` is
# treated as unparseable. MUST match `SUBAGENT_PAYLOAD_VERSION` in
# `extensions/sculptor_subagent.ts`.
SUBAGENT_PAYLOAD_VERSION: int = 1

# Top-level key under which the completion payload rides the `notify` message
# string. MUST match `SUBAGENT_NOTIFY_MARKER` in `extensions/sculptor_subagent.ts`.
SUBAGENT_NOTIFY_MARKER: str = "sculptorSubagentTask"


class SubagentChildEvent(BaseModel):
    """One ordered lifecycle event from a child pi process."""

    seq: int
    kind: str  # "tool_call" | "tool_result" | "text"
    text: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = {}
    is_error: bool = False


class SubagentChild(BaseModel):
    """A single child sub-agent's accumulated lifecycle snapshot."""

    child_id: str
    label: str = "subagent"
    task: str = ""
    status: str = "running"
    stop_reason: str | None = None
    exit_code: int | None = None
    events: list[SubagentChildEvent] = []


class SubagentStart(BaseModel):
    """The launch snapshot from a `subagent` tool's result `details`."""

    task_id: str
    tool_call_id: str
    label: str = "subagent"
    # Each detached child's process-group id (pgid == pid). The adapter records
    # them so a shutdown can SIGTERM each group in the environment without
    # touching the pi process. May be empty if no child produced a pid.
    pgids: tuple[int, ...] = ()
    count: int = 0
    status: str = "running"


class SubagentCompletion(BaseModel):
    """The completion snapshot from the out-of-band `notify` marker."""

    task_id: str
    tool_call_id: str
    status: str
    children: list[SubagentChild] = []


def _coerce_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_event(raw: Any) -> SubagentChildEvent | None:
    """Parse one child event defensively; return None to skip a malformed entry."""
    if not isinstance(raw, dict):
        return None
    seq = raw.get("seq")
    kind = raw.get("kind")
    if not isinstance(seq, int) or isinstance(seq, bool) or not isinstance(kind, str):
        return None
    args = raw.get("args")
    return SubagentChildEvent(
        seq=seq,
        kind=kind,
        text=raw.get("text") if isinstance(raw.get("text"), str) else "",
        tool_call_id=raw.get("toolCallId") if isinstance(raw.get("toolCallId"), str) else "",
        tool_name=raw.get("toolName") if isinstance(raw.get("toolName"), str) else "",
        args=args if isinstance(args, dict) else {},
        is_error=bool(raw.get("isError", False)),
    )


def _parse_child(raw: Any) -> SubagentChild | None:
    if not isinstance(raw, dict):
        return None
    child_id = raw.get("childId")
    if not isinstance(child_id, str) or not child_id:
        return None
    raw_events = raw.get("events")
    events: list[SubagentChildEvent] = []
    if isinstance(raw_events, list):
        for entry in raw_events:
            event = _parse_event(entry)
            if event is not None:
                events.append(event)
    # Sort by seq so out-of-order events render in producer order.
    events.sort(key=lambda event: event.seq)
    status = raw.get("status")
    return SubagentChild(
        child_id=child_id,
        label=raw.get("label") if isinstance(raw.get("label"), str) and raw.get("label") else "subagent",
        task=raw.get("task") if isinstance(raw.get("task"), str) else "",
        status=status if isinstance(status, str) else "running",
        stop_reason=raw.get("stopReason") if isinstance(raw.get("stopReason"), str) else None,
        exit_code=_coerce_int(raw.get("exitCode")),
        events=events,
    )


def _parse_children(raw_children: Any) -> list[SubagentChild]:
    children: list[SubagentChild] = []
    if isinstance(raw_children, list):
        for entry in raw_children:
            child = _parse_child(entry)
            if child is not None:
                children.append(child)
    return children


def parse_subagent_start(payload: Any) -> SubagentStart | None:
    """Parse the `subagent` tool result envelope into a launch snapshot.

    `payload` is a `tool_execution_end.result` — the `{content, details}`
    envelope. The structured task lives under `details.task`. Returns `None`
    (the call then renders as an ordinary tool with no sub-agent lifecycle)
    when the envelope carries no recognized, version-matched task.
    """
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    if details.get("v") != SUBAGENT_PAYLOAD_VERSION:
        return None
    task = details.get("task")
    if not isinstance(task, dict):
        return None
    task_id = task.get("taskId")
    tool_call_id = task.get("toolCallId")
    if not isinstance(task_id, str) or not task_id:
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    raw_pgids = task.get("pgids")
    pgids: tuple[int, ...] = ()
    if isinstance(raw_pgids, list):
        pgids = tuple(p for p in (_coerce_int(entry) for entry in raw_pgids) if p is not None and p > 0)
    count = _coerce_int(task.get("count"))
    return SubagentStart(
        task_id=task_id,
        tool_call_id=tool_call_id,
        label=task.get("label") if isinstance(task.get("label"), str) and task.get("label") else "subagent",
        pgids=pgids,
        count=count if count is not None else 0,
        status=task.get("status") if isinstance(task.get("status"), str) else "running",
    )


def parse_subagent_completion(message: Any) -> SubagentCompletion | None:
    """Parse a `notify` message string into a completion snapshot.

    `message` is the `extension_ui_request.message` of a fire-and-forget
    `notify`. It is JSON carrying `{SUBAGENT_NOTIFY_MARKER: {...}}`, under which
    the full per-child snapshot rides. Returns `None` for any notify that is not
    our sub-agent marker (a foreign/ordinary notify, or the background marker),
    so the caller can ignore it.
    """
    if not isinstance(message, str) or not message:
        return None
    try:
        decoded = json.loads(message)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    payload = decoded.get(SUBAGENT_NOTIFY_MARKER)
    if not isinstance(payload, dict):
        return None
    if payload.get("v") != SUBAGENT_PAYLOAD_VERSION:
        return None
    task_id = payload.get("taskId")
    tool_call_id = payload.get("toolCallId")
    status = payload.get("status")
    if not isinstance(task_id, str) or not task_id:
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    if not isinstance(status, str) or not status:
        return None
    return SubagentCompletion(
        task_id=task_id,
        tool_call_id=tool_call_id,
        status=status,
        children=_parse_children(payload.get("children")),
    )


def build_child_content_blocks(child: SubagentChild, parent_tool_call_id: str) -> tuple[ContentBlockTypes, ...]:
    """Render one child's events as interleaved nested blocks.

    A child's own tool calls map through the same pi→Claude adapter the main
    loop uses (`tool_rendering`), so a child `read` renders as a `Read` block
    exactly like a top-level one; text events become `TextBlock`s. Child
    tool-call ids are namespaced under the parent + child so they can never
    collide with a main-loop tool id (or another child's), keeping the
    ToolUse/ToolResult pairing unambiguous when message_conversion builds the
    nested ChatMessage.
    """
    blocks: list[ContentBlockTypes] = []
    for event in child.events:
        if event.kind == "text":
            if event.text:
                blocks.append(TextBlock(text=event.text))
        elif event.kind == "tool_call":
            claude_name, claude_input = map_pi_tool_call(event.tool_name, event.args)
            blocks.append(
                ToolUseBlock(
                    id=ToolUseID(_namespaced_id(parent_tool_call_id, child.child_id, event.tool_call_id)),
                    name=claude_name,
                    input=claude_input,
                )
            )
        elif event.kind == "tool_result":
            claude_name, claude_input = map_pi_tool_call(event.tool_name, event.args)
            blocks.append(
                ToolResultBlock(
                    tool_use_id=ToolUseID(_namespaced_id(parent_tool_call_id, child.child_id, event.tool_call_id)),
                    tool_name=claude_name,
                    invocation_string=get_tool_invocation_string(claude_name, claude_input),
                    content=GenericToolContent(text=event.text),
                    is_error=event.is_error,
                )
            )
    # A child with no events still surfaces as an attributed bubble (e.g. an
    # aborted child).
    if not blocks:
        blocks.append(TextBlock(text=_empty_child_text(child)))
    return tuple(blocks)


def _namespaced_id(parent_tool_call_id: str, child_id: str, child_tool_call_id: str) -> str:
    return f"{parent_tool_call_id}:{child_id}:{child_tool_call_id}"


def _empty_child_text(child: SubagentChild) -> str:
    if child.status == "error":
        return f"Sub-agent {child.label} failed{f' ({child.stop_reason})' if child.stop_reason else ''}."
    if child.status == "running":
        return f"Sub-agent {child.label} did not finish."
    return f"Sub-agent {child.label} produced no output."
