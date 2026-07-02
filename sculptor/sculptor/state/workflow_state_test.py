from sculptor.state.workflow_state import WorkflowAgentProgress
from sculptor.state.workflow_state import WorkflowPhaseProgress
from sculptor.state.workflow_state import merge_workflow_progress_entries
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


def test_parse_workflow_progress_entries_dedupes_repeated_indexes_keeping_last_state() -> None:
    """The wire tree is event-log shaped: the same agent index reappears with
    updated state (queued, then started, then progress). Only the last
    occurrence must survive, at the position where the entry first appeared."""
    entries = parse_workflow_progress_entries(
        [
            {"type": "workflow_phase", "index": 1, "title": "Recon"},
            {"type": "workflow_agent", "index": 1, "label": "count-files", "phaseIndex": 1, "state": "start"},
            {"type": "workflow_agent", "index": 2, "label": "read-readme", "phaseIndex": 1, "state": "start"},
            {
                "type": "workflow_agent",
                "index": 1,
                "label": "count-files",
                "phaseIndex": 1,
                "state": "progress",
                "startedAt": 1783017018742,
            },
            {
                "type": "workflow_agent",
                "index": 2,
                "label": "read-readme",
                "phaseIndex": 1,
                "state": "done",
                "resultPreview": '{"firstLine":"# Test Project"}',
            },
        ]
    )
    assert entries is not None
    assert len(entries) == 3
    phase, count_files, read_readme = entries
    assert isinstance(phase, WorkflowPhaseProgress)
    assert isinstance(count_files, WorkflowAgentProgress)
    assert count_files.state == "progress"
    assert count_files.started_at == 1783017018742
    assert isinstance(read_readme, WorkflowAgentProgress)
    assert read_readme.state == "done"
    assert read_readme.result_preview == '{"firstLine":"# Test Project"}'


def test_parse_workflow_progress_entries_dedupes_phases_and_agents_in_separate_index_spaces() -> None:
    """Phase index 0 and agent index 0 are different entries and must both survive."""
    entries = parse_workflow_progress_entries(
        [
            {"type": "workflow_phase", "index": 0, "title": "Review"},
            {"type": "workflow_agent", "index": 0, "label": "review:bugs", "phaseIndex": 0},
        ]
    )
    assert entries is not None
    assert len(entries) == 2


def test_merge_workflow_progress_entries_accumulates_deltas_across_payloads() -> None:
    """The CLI streams deltas: later payloads carry only the entries whose
    state changed. Merging must keep untouched entries and update changed
    ones in place."""
    initial = parse_workflow_progress_entries(
        [
            {"type": "workflow_phase", "index": 1, "title": "Recon"},
            {"type": "workflow_agent", "index": 1, "label": "count-files", "phaseIndex": 1, "state": "progress"},
            {"type": "workflow_agent", "index": 2, "label": "read-readme", "phaseIndex": 1, "state": "progress"},
        ]
    )
    delta = parse_workflow_progress_entries(
        [
            {
                "type": "workflow_agent",
                "index": 2,
                "label": "read-readme",
                "phaseIndex": 1,
                "state": "done",
                "resultPreview": '{"firstLine":"# Test Project"}',
            }
        ]
    )
    assert initial is not None and delta is not None

    merged = merge_workflow_progress_entries(initial, delta)

    assert len(merged) == 3
    phase, count_files, read_readme = merged
    assert isinstance(phase, WorkflowPhaseProgress)
    assert isinstance(count_files, WorkflowAgentProgress)
    assert count_files.state == "progress"
    assert isinstance(read_readme, WorkflowAgentProgress)
    assert read_readme.state == "done"
    assert read_readme.result_preview == '{"firstLine":"# Test Project"}'


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
