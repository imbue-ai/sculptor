"""Tests for the sub-agent structured-progress parser and nested-block builder.

Fixtures follow the wire shape `extensions/sculptor_subagent.ts` emits under a
tool result envelope's `details`: `{v, children:[{childId, label, task, status,
events:[...]}]}`. The parser must be permissive (the payload crosses a
subprocess boundary) and idempotent (partialResult is accumulated, re-sent
whole on every update).
"""

from __future__ import annotations

from sculptor.agents.pi_agent.subagent import SUBAGENT_PAYLOAD_VERSION
from sculptor.agents.pi_agent.subagent import build_child_content_blocks
from sculptor.agents.pi_agent.subagent import parse_subagent_progress
from sculptor.state.chat_state import GenericToolContent
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock


def _envelope(details: object) -> dict:
    """Wrap structured `details` in the {content, details} result envelope."""
    return {"content": [{"type": "text", "text": "summary"}], "details": details}


def _child(child_id: str = "c0", **overrides: object) -> dict:
    base: dict = {
        "childId": child_id,
        "label": "subagent",
        "task": "do a thing",
        "status": "done",
        "stopReason": "stop",
        "exitCode": 0,
        "events": [
            {"seq": 0, "kind": "tool_call", "toolCallId": "t1", "toolName": "read", "args": {"path": "/etc/hosts"}},
            {"seq": 1, "kind": "tool_result", "toolCallId": "t1", "text": "127.0.0.1 localhost", "isError": False},
            {"seq": 2, "kind": "text", "text": "The file has 1 line."},
        ],
    }
    base.update(overrides)
    return base


def test_parse_well_formed_single_child() -> None:
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [_child()]}))
    assert progress is not None
    assert len(progress.children) == 1
    child = progress.children[0]
    assert child.child_id == "c0"
    assert child.status == "done"
    assert child.is_terminal is True
    assert [event.kind for event in child.events] == ["tool_call", "tool_result", "text"]
    assert child.events[0].tool_name == "read"
    assert child.events[0].args == {"path": "/etc/hosts"}


def test_parse_reorders_events_by_seq() -> None:
    # A coalesced / out-of-order snapshot must still render in producer order.
    scrambled = _child(
        events=[
            {"seq": 2, "kind": "text", "text": "done"},
            {"seq": 0, "kind": "tool_call", "toolCallId": "t1", "toolName": "bash", "args": {"command": "ls"}},
            {"seq": 1, "kind": "tool_result", "toolCallId": "t1", "text": "a\nb", "isError": False},
        ]
    )
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [scrambled]}))
    assert progress is not None
    assert [event.seq for event in progress.children[0].events] == [0, 1, 2]
    assert [event.kind for event in progress.children[0].events] == ["tool_call", "tool_result", "text"]


def test_parse_version_mismatch_returns_none() -> None:
    # An extension/binary skew must degrade to plain rendering, never mis-parse.
    assert parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION + 1, "children": [_child()]})) is None


def test_parse_missing_details_returns_none() -> None:
    assert parse_subagent_progress({"content": [{"type": "text", "text": "x"}]}) is None
    assert parse_subagent_progress({"content": [], "details": "not-a-dict"}) is None
    assert parse_subagent_progress(None) is None
    assert parse_subagent_progress("bare string") is None


def test_parse_skips_malformed_children_and_events() -> None:
    payload = {
        "v": SUBAGENT_PAYLOAD_VERSION,
        "children": [
            "not-a-dict",
            {"label": "no id"},  # missing childId -> skipped
            {
                "childId": "c1",
                "status": "running",
                "events": [
                    {"kind": "text", "text": "no seq"},  # missing seq -> skipped
                    {"seq": 0, "kind": "text", "text": "kept"},
                    "garbage",
                ],
            },
        ],
    }
    progress = parse_subagent_progress(_envelope(payload))
    assert progress is not None
    assert len(progress.children) == 1
    child = progress.children[0]
    assert child.child_id == "c1"
    assert child.status == "running"
    assert child.is_terminal is False
    assert [event.text for event in child.events] == ["kept"]


def test_parse_truncated_events_tolerated() -> None:
    # A child whose events array is empty (truncated mid-stream) still parses.
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [_child(events=[])]}))
    assert progress is not None
    assert progress.children[0].events == []


def test_build_child_blocks_renders_nested_tool_and_text() -> None:
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [_child()]}))
    assert progress is not None
    use_block, result_block, text_block = build_child_content_blocks(
        progress.children[0], parent_tool_call_id="parent-1"
    )
    assert isinstance(use_block, ToolUseBlock)
    assert use_block.name == "Read"  # child tool mapped through the pi->Claude adapter
    assert isinstance(result_block, ToolResultBlock)
    assert isinstance(result_block.content, GenericToolContent)
    assert result_block.content.text == "127.0.0.1 localhost"
    assert isinstance(text_block, TextBlock)
    assert text_block.text == "The file has 1 line."


def test_build_child_blocks_namespaces_tool_ids() -> None:
    # Child tool ids are namespaced under parent+child so they can never collide
    # with a main-loop tool id, and the ToolUse/ToolResult pair stays matched.
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [_child()]}))
    assert progress is not None
    blocks = build_child_content_blocks(progress.children[0], parent_tool_call_id="parent-1")
    use_block = blocks[0]
    result_block = blocks[1]
    assert isinstance(use_block, ToolUseBlock)
    assert isinstance(result_block, ToolResultBlock)
    assert str(use_block.id) == "parent-1:c0:t1"
    assert str(result_block.tool_use_id) == str(use_block.id)


def test_build_child_blocks_error_result_flagged() -> None:
    child = _child(
        events=[
            {"seq": 0, "kind": "tool_call", "toolCallId": "t1", "toolName": "bash", "args": {"command": "false"}},
            {"seq": 1, "kind": "tool_result", "toolCallId": "t1", "text": "boom", "isError": True},
        ]
    )
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [child]}))
    assert progress is not None
    blocks = build_child_content_blocks(progress.children[0], parent_tool_call_id="p")
    result_block = blocks[1]
    assert isinstance(result_block, ToolResultBlock)
    assert result_block.is_error is True


def test_build_child_blocks_empty_child_gets_attributed_text() -> None:
    # A child that produced no events still surfaces as an attributed bubble.
    child = _child(status="error", stopReason="aborted", exitCode=137, events=[])
    progress = parse_subagent_progress(_envelope({"v": SUBAGENT_PAYLOAD_VERSION, "children": [child]}))
    assert progress is not None
    blocks = build_child_content_blocks(progress.children[0], parent_tool_call_id="p")
    assert len(blocks) == 1
    text_block = blocks[0]
    assert isinstance(text_block, TextBlock)
    assert "failed" in text_block.text.lower()
