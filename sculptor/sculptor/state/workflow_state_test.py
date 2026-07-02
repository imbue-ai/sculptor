from sculptor.state.workflow_state import WorkflowAgentProgress
from sculptor.state.workflow_state import WorkflowPhaseProgress
from sculptor.state.workflow_state import parse_workflow_progress_entries


def _make_wire_agent_entry() -> dict:
    """A workflow_agent entry as the CLI emits it (camelCase keys)."""
    return {
        "type": "workflow_agent",
        "index": 0,
        "label": "review:bugs",
        "phaseIndex": 0,
        "phaseTitle": "Review",
        "model": "claude-fable-5",
        "state": "progress",
        "queuedAt": 1748471200000,
        "startedAt": 1748471201000,
        "lastProgressAt": 1748471263000,
        "promptPreview": "Review the diff for bugs",
        "tokens": 31200,
        "toolCalls": 11,
        "durationMs": 61200,
        "lastToolSummary": "Grep: TODO in src/",
    }


def test_parse_workflow_progress_entries_returns_none_for_absent_payload() -> None:
    """Absent workflow_progress means "unchanged", which must stay distinct from an empty tree."""
    assert parse_workflow_progress_entries(None) is None
    assert parse_workflow_progress_entries([]) == ()


def test_parse_workflow_progress_entries_parses_phases_and_agents_from_camel_case_wire_format() -> None:
    entries = parse_workflow_progress_entries(
        [
            {"type": "workflow_phase", "index": 0, "title": "Review", "kind": ""},
            _make_wire_agent_entry(),
        ]
    )
    assert entries is not None
    phase, agent = entries
    assert isinstance(phase, WorkflowPhaseProgress)
    assert phase.title == "Review"
    assert isinstance(agent, WorkflowAgentProgress)
    assert agent.label == "review:bugs"
    assert agent.phase_index == 0
    assert agent.phase_title == "Review"
    assert agent.state == "progress"
    assert agent.tokens == 31200
    assert agent.tool_calls == 11
    assert agent.duration_ms == 61200
    assert agent.last_tool_summary == "Grep: TODO in src/"


def test_parse_workflow_progress_entries_skips_log_and_unknown_entry_types() -> None:
    entries = parse_workflow_progress_entries(
        [
            {"type": "workflow_log", "message": "3/10 found"},
            {"type": "workflow_future_thing", "index": 0},
            "not even a dict",
            _make_wire_agent_entry(),
        ]
    )
    assert entries is not None
    assert len(entries) == 1
    assert isinstance(entries[0], WorkflowAgentProgress)


def test_parse_workflow_progress_entries_tolerates_unknown_fields_on_known_entry_types() -> None:
    agent_entry = _make_wire_agent_entry()
    agent_entry["someFutureField"] = {"nested": True}
    entries = parse_workflow_progress_entries([agent_entry])
    assert entries is not None
    assert len(entries) == 1


def test_parse_workflow_progress_entries_skips_malformed_entries_without_raising() -> None:
    entries = parse_workflow_progress_entries(
        [
            {"type": "workflow_agent", "index": "not-an-int"},
            {"type": "workflow_phase", "index": 1, "title": "Verify"},
        ]
    )
    assert entries is not None
    assert len(entries) == 1
    assert isinstance(entries[0], WorkflowPhaseProgress)


def test_parse_workflow_progress_entries_keeps_wire_order_across_phases_and_agents() -> None:
    entries = parse_workflow_progress_entries(
        [
            {"type": "workflow_phase", "index": 0, "title": "Find"},
            {"type": "workflow_phase", "index": 1, "title": "Verify"},
            _make_wire_agent_entry(),
        ]
    )
    assert entries is not None
    assert [type(e).__name__ for e in entries] == [
        "WorkflowPhaseProgress",
        "WorkflowPhaseProgress",
        "WorkflowAgentProgress",
    ]
