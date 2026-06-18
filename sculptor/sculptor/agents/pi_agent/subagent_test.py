"""Tests for the sub-agent lifecycle parsers and nested-block builder.

The `subagent` tool yields immediately (a launch snapshot under the tool result
`details.task`) and reports the full per-child snapshot out-of-band via a
`notify` marker on completion. Both payloads are parsed here. Parsing must be
permissive (the payloads cross a subprocess / extension boundary), degrading to
`None` rather than mis-parsing on skew.
"""

from __future__ import annotations

import json

from sculptor.agents.pi_agent.subagent import SUBAGENT_NOTIFY_MARKER
from sculptor.agents.pi_agent.subagent import SUBAGENT_PAYLOAD_VERSION
from sculptor.agents.pi_agent.subagent import build_child_content_blocks
from sculptor.agents.pi_agent.subagent import parse_subagent_completion
from sculptor.agents.pi_agent.subagent import parse_subagent_start
from sculptor.state.chat_state import GenericToolContent
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock


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


def _completion_message(children: list, status: str = "completed", **overrides: object) -> str:
    """The `notify` message string carrying the completion marker."""
    payload: dict = {
        "v": SUBAGENT_PAYLOAD_VERSION,
        "taskId": "sat_sa1",
        "toolCallId": "sa1",
        "status": status,
        "children": children,
    }
    payload.update(overrides)
    return json.dumps({SUBAGENT_NOTIFY_MARKER: payload})


def _start_envelope(**task_overrides: object) -> dict:
    """The `{content, details: {v, task}}` launch result envelope."""
    task: dict = {
        "taskId": "sat_sa1",
        "toolCallId": "sa1",
        "label": "2 sub-agents",
        "pgids": [4242, 4343],
        "count": 2,
        "status": "running",
    }
    task.update(task_overrides)
    return {
        "content": [{"type": "text", "text": "Started 2 sub-agent(s)"}],
        "details": {"v": SUBAGENT_PAYLOAD_VERSION, "task": task},
    }


# --- launch (start) parsing ------------------------------------------------


def test_parse_start_well_formed() -> None:
    started = parse_subagent_start(_start_envelope())
    assert started is not None
    assert started.task_id == "sat_sa1"
    assert started.tool_call_id == "sa1"
    assert started.label == "2 sub-agents"
    assert started.pgids == (4242, 4343)
    assert started.count == 2
    assert started.status == "running"


def test_parse_start_drops_nonpositive_pgids() -> None:
    # A child that produced no pid coerces away; only real groups are tracked.
    started = parse_subagent_start(_start_envelope(pgids=[0, -1, 99, "x"]))
    assert started is not None
    assert started.pgids == (99,)


def test_parse_start_rejects_skew_and_malformed() -> None:
    assert parse_subagent_start(_start_envelope(taskId="")) is None  # empty id
    assert parse_subagent_start({"content": [], "details": {"v": SUBAGENT_PAYLOAD_VERSION}}) is None  # no task
    assert parse_subagent_start({"content": [], "details": {"v": SUBAGENT_PAYLOAD_VERSION + 1, "task": {}}}) is None
    assert parse_subagent_start({"content": [{"type": "text", "text": "x"}]}) is None  # no details
    assert parse_subagent_start(None) is None


# --- completion parsing ----------------------------------------------------


def test_parse_completion_well_formed_single_child() -> None:
    completion = parse_subagent_completion(_completion_message([_child()]))
    assert completion is not None
    assert completion.task_id == "sat_sa1"
    assert completion.tool_call_id == "sa1"
    assert completion.status == "completed"
    assert len(completion.children) == 1
    child = completion.children[0]
    assert child.child_id == "c0"
    assert child.status == "done"
    assert [event.kind for event in child.events] == ["tool_call", "tool_result", "text"]
    assert child.events[0].tool_name == "read"
    assert child.events[0].args == {"path": "/etc/hosts"}


def test_parse_completion_reorders_events_by_seq() -> None:
    # A coalesced / out-of-order snapshot must still render in producer order.
    scrambled = _child(
        events=[
            {"seq": 2, "kind": "text", "text": "done"},
            {"seq": 0, "kind": "tool_call", "toolCallId": "t1", "toolName": "bash", "args": {"command": "ls"}},
            {"seq": 1, "kind": "tool_result", "toolCallId": "t1", "text": "a\nb", "isError": False},
        ]
    )
    completion = parse_subagent_completion(_completion_message([scrambled]))
    assert completion is not None
    assert [event.seq for event in completion.children[0].events] == [0, 1, 2]
    assert [event.kind for event in completion.children[0].events] == ["tool_call", "tool_result", "text"]


def test_parse_completion_version_mismatch_returns_none() -> None:
    # An extension/binary skew must degrade to no sub-agent lifecycle, never mis-parse.
    assert parse_subagent_completion(_completion_message([_child()], v=SUBAGENT_PAYLOAD_VERSION + 1)) is None


def test_parse_completion_ignores_foreign_notify() -> None:
    # A notify that is not our marker (a background-task notify, an ordinary
    # status notify, malformed JSON, or a non-string) is ignored.
    assert parse_subagent_completion(json.dumps({"sculptorBackgroundTask": {"v": 1}})) is None
    assert parse_subagent_completion(json.dumps({"somethingElse": {"v": 1}})) is None
    assert parse_subagent_completion("not json") is None
    assert parse_subagent_completion("") is None
    assert parse_subagent_completion(None) is None


def test_parse_completion_requires_ids_and_status() -> None:
    assert parse_subagent_completion(_completion_message([_child()], taskId="")) is None
    assert parse_subagent_completion(_completion_message([_child()], toolCallId="")) is None
    assert parse_subagent_completion(_completion_message([_child()], status="")) is None


def test_parse_completion_skips_malformed_children_and_events() -> None:
    children = [
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
    ]
    completion = parse_subagent_completion(_completion_message(children))
    assert completion is not None
    assert len(completion.children) == 1
    child = completion.children[0]
    assert child.child_id == "c1"
    assert child.status == "running"
    assert [event.text for event in child.events] == ["kept"]


# --- nested block building -------------------------------------------------


def _parse_one_child(child: dict):
    completion = parse_subagent_completion(_completion_message([child]))
    assert completion is not None
    return completion.children[0]


def test_build_child_blocks_renders_nested_tool_and_text() -> None:
    use_block, result_block, text_block = build_child_content_blocks(
        _parse_one_child(_child()), parent_tool_call_id="parent-1"
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
    blocks = build_child_content_blocks(_parse_one_child(_child()), parent_tool_call_id="parent-1")
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
    blocks = build_child_content_blocks(_parse_one_child(child), parent_tool_call_id="p")
    result_block = blocks[1]
    assert isinstance(result_block, ToolResultBlock)
    assert result_block.is_error is True


def test_build_child_blocks_empty_child_gets_attributed_text() -> None:
    # A child that produced no events still surfaces as an attributed bubble.
    child = _child(status="error", stopReason="aborted", exitCode=137, events=[])
    blocks = build_child_content_blocks(_parse_one_child(child), parent_tool_call_id="p")
    assert len(blocks) == 1
    text_block = blocks[0]
    assert isinstance(text_block, TextBlock)
    assert "failed" in text_block.text.lower()
