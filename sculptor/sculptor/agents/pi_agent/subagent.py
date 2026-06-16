"""Parse the Sculptor sub-agent extension's structured per-child progress.

pi-core has no sub-agent protocol surface, so Sculptor ships a pinned extension
(`extensions/sculptor_subagent.ts`) that registers a `subagent` tool. The tool
spawns each child as its own `pi` process and emits, over the parent tool's
streaming result (`tool_execution_update.partialResult` / the final
`tool_execution_end.result`), a STRUCTURED per-child lifecycle payload under the
result envelope's `details`:

    {"v": 1, "children": [
        {"childId", "label", "task", "status": "running"|"done"|"error",
         "stopReason"?, "exitCode"?,
         "events": [
             {"seq", "kind": "tool_call",   "toolCallId", "toolName", "args"},
             {"seq", "kind": "tool_result", "toolCallId", "text", "isError"},
             {"seq", "kind": "text",        "text"}]}]}

The structured shape lets the adapter render each child's activity as nested,
attributed blocks — a parent `Agent` tool with the child's own tool calls and
text grouped beneath it (`parent_tool_use_id`), matching Claude's sub-agent
rendering.

`partialResult` is ACCUMULATED, not a delta: each update re-sends the full
children/events snapshot, so this module re-parses the whole value idempotently
(it never appends). Parsing is permissive — the payload crosses a subprocess
boundary, so a malformed value or unknown version yields `None` (the call then
renders as a plain `Agent` tool block) and a bad event is skipped.

Wire contract shared with `extensions/sculptor_subagent.ts`: the version and
field names below MUST match what that extension emits. Changing one means
editing both in the same change.
"""

from __future__ import annotations

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

# Child statuses that mean the child has finished.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "error"})


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

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


class SubagentProgress(BaseModel):
    """The full, re-parseable per-update snapshot of all children."""

    version: int
    children: list[SubagentChild] = []


def _coerce_int(value: Any) -> int | None:
    return value if isinstance(value, bool) is False and isinstance(value, int) else None


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


def parse_subagent_progress(payload: Any) -> SubagentProgress | None:
    """Re-parse the full accumulated sub-agent payload from a result envelope.

    `payload` is a `tool_execution_update.partialResult` or
    `tool_execution_end.result` — the `{content, details}` envelope. The
    structured progress lives under `details`. Returns `None` (degrade to plain
    rendering) when the envelope carries no recognized, version-matched payload.
    """
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if not isinstance(details, dict):
        return None
    if details.get("v") != SUBAGENT_PAYLOAD_VERSION:
        return None
    raw_children = details.get("children")
    children: list[SubagentChild] = []
    if isinstance(raw_children, list):
        for entry in raw_children:
            child = _parse_child(entry)
            if child is not None:
                children.append(child)
    return SubagentProgress(version=SUBAGENT_PAYLOAD_VERSION, children=children)


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
