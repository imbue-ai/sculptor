"""Integration tests for the floating agent-tasks widget inside the StatusPill.

The legacy ``TodoListPanel`` was deprecated and the agent-tasks UI was merged
into the alpha-chat status pill. When the task list is live the pill's label
is replaced with the current in-progress task; hover/click on the pill reveals
a popover containing the full task list. After every task completes the pill
lingers briefly with a "X of N done" summary before reverting to the ordinary
status label.

Source of truth for the on-disk task store is Claude Code's per-task JSON files
at ``~/.claude/tasks/{session_id}/{id}.json``. FakeClaude's ``task_create`` /
``task_update`` handlers write those files before emitting the matching
TaskCreate / TaskUpdate tool_use + tool_result blocks; the backend's
``_read_task_list_artifact`` re-reads the directory on every refresh trigger.

These tests cover the user-visible scenarios that survive end-to-end:
* S1: linear task flow (no DAG affordances)
* S6: chat-transcript inline TaskCreate / TaskUpdate pills, plus hidden tools
* S7: empty / single-task popover states
* malformed per-task JSON tolerated
* Scenario 3: hover opens the popover
* Scenario 4: click pins the popover, second click unpins
* Scenario 5/6: post-completion count summary stays after the turn ends
* The "empty state" popover affordance that exists before any TaskCreate

The deeper phase-machine invariants (active → lingering transitions,
turn-id reset, lifecycle-state overrides) are covered exhaustively by
``StatusPill.test.tsx``. The mid-stream "in-progress task name in the pill
label" path is too tightly coupled to artifact-sync timing to assert
deterministically from Playwright, so it lives in the unit tests.

The version-2 legacy fallback is covered by
``sculptor/sculptor/web/typed_artifact_data_test.py`` at the
unit-test level; round-tripping a stale on-disk artifact through the agent
process from FakeClaude is too invasive for the value it adds.
"""

import json

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tasks_popover import PlaywrightAgentTasksPopoverElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A multi-step payload that mirrors a mid-implementation state: one task done,
# one in-flight, one queued. After the turn finishes, ``hasFreshTasks`` is
# true (not stale, not all-complete) so the pill stays visible with the
# count summary.
_PARTIAL_PROGRESS_TASKS = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Step 1", "status": "completed", "activeForm": "Working on Step 1"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Step 2", "status": "in_progress", "activeForm": "Working on Step 2"}},
    {"command": "task_create", "args": {"id": "3", "subject": "Step 3", "status": "pending", "activeForm": "Working on Step 3"}}
  ]
}`"""

_ALL_COMPLETE_TASKS = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_update", "args": {"id": "2", "status": "completed"}},
    {"command": "task_update", "args": {"id": "3", "status": "completed"}}
  ]
}`"""

_LINEAR_FOUR_TASKS = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "A", "status": "completed"}},
    {"command": "task_create", "args": {"id": "2", "subject": "B", "status": "completed"}},
    {"command": "task_create", "args": {"id": "3", "subject": "C", "status": "in_progress"}},
    {"command": "task_create", "args": {"id": "4", "subject": "D", "status": "pending"}}
  ]
}`"""

_SINGLE_TASK = """\
fake_claude:task_create `{"id": "1", "subject": "Only task", "status": "in_progress"}`"""

_HIDDEN_TASK_TOOLS = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Visible task", "status": "in_progress"}},
    {"command": "task_list", "args": {}},
    {"command": "task_get", "args": {"id": "1"}}
  ]
}`"""


@user_story("to see the tasks popover even before the agent emits a TaskCreate")
def test_empty_state_popover_before_tasks_arrive(sculptor_instance_: SculptorInstance) -> None:
    """The popover trigger is available whenever the pill is on screen.

    Even before the agent calls TaskCreate, hovering/clicking the pill should
    surface an EmptyState ("No agent tasks yet"), so users can discover the
    tasks affordance.
    """
    page = sculptor_instance_.page

    # No TaskCreate — a long-running bash step so the pill stays visible.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "sleep 30"}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    status_pill.click()
    expect(agent_tasks.get_empty_state()).to_be_visible()


@user_story("to see a 'X of N done' summary on the pill after the agent emits a TaskCreate")
def test_status_pill_shows_count_summary_after_turn(sculptor_instance_: SculptorInstance) -> None:
    """Once a task list exists, the pill remains visible post-turn.

    With at least one task completed and the artifact considered fresh (not
    a stale carryover from a prior turn), the pill shows the compact
    "X of N done" summary instead of disappearing — so users can still
    hover/click to review the list.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARTIAL_PROGRESS_TASKS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    # Wait for the user message + the agent's tool-call message to be
    # committed. We don't wait for the pill to disappear (it shouldn't —
    # that's exactly the new behavior under test).
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    label = chat_panel.get_status_pill_label()
    expect(label).to_contain_text("1 of 3 done")


@user_story("to peek at the full task list by hovering the status pill")
def test_hover_opens_tasks_popover(sculptor_instance_: SculptorInstance) -> None:
    """Hovering the pill should reveal a popover listing every task.

    Uses the post-turn count-summary state (rather than mid-stream) because
    the popover's contents are the same regardless of phase and the
    post-turn state is deterministic.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARTIAL_PROGRESS_TASKS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    status_pill.hover()
    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("Step 1")
    expect(rows.nth(1)).to_contain_text("Step 2")
    expect(rows.nth(2)).to_contain_text("Step 3")


@user_story("to keep the task list visible by clicking the status pill to pin it")
def test_click_pins_tasks_popover(sculptor_instance_: SculptorInstance) -> None:
    """A click pins the popover open. A second click closes it."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARTIAL_PROGRESS_TASKS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    rows = agent_tasks.get_rows()

    # Pinning persists across hover-leave.
    status_pill.click()
    expect(rows).to_have_count(3)
    page.mouse.move(0, 0)
    expect(rows).to_have_count(3)

    # Second click on the pill unpins → popover closes.
    status_pill.click()
    page.mouse.move(0, 0)
    expect(rows).to_have_count(0)


@user_story("to dismiss the pinned task popover by clicking outside of it")
def test_outside_click_closes_pinned_popover(sculptor_instance_: SculptorInstance) -> None:
    """Clicking outside the pinned popover dismisses it."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARTIAL_PROGRESS_TASKS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    status_pill.click()
    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(3)

    # Click somewhere outside the popover and pill.
    page.mouse.click(10, 10)
    expect(rows).to_have_count(0)


@user_story("to see the count summary update after a follow-up TaskUpdate completes every task")
def test_count_summary_updates_on_follow_up(sculptor_instance_: SculptorInstance) -> None:
    """After a follow-up turn marks every task done, the pill reflects 'N of N done'."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PARTIAL_PROGRESS_TASKS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    label = chat_panel.get_status_pill_label()
    expect(label).to_contain_text("1 of 3 done")

    send_chat_message(chat_panel=chat_panel, message=_ALL_COMPLETE_TASKS)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    expect(label).to_contain_text("3 of 3 done")


@user_story("S1: to see a flat list when tasks have no dependencies")
def test_linear_task_flow_renders_flat_list(sculptor_instance_: SculptorInstance) -> None:
    """Four linear tasks render as a flat list with no DAG affordances.

    Asserts the panel does NOT render the waiting-on badge or graph-toggle
    button when every task has empty blocks / blockedBy. Those affordances
    are reserved for non-linear DAGs (Phase 6+).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_LINEAR_FOUR_TASKS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(4)
    expect(agent_tasks.get_waiting_badges()).to_have_count(0)
    expect(agent_tasks.get_graph_toggle()).to_have_count(0)


@user_story("S6: to see TaskCreate and TaskUpdate inline in the chat transcript")
def test_chat_transcript_shows_task_create_and_update(sculptor_instance_: SculptorInstance) -> None:
    """TaskCreate / TaskUpdate render as visible tool pills in the chat transcript."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Investigate", "status": "in_progress"}},
    {"command": "task_update", "args": {"id": "1", "status": "completed"}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # The transcript should expose two tool pills (one per TaskCreate / TaskUpdate).
    # AlphaToolPill labels are the raw tool names; the "Added task" /
    # "Updated task" display strings only appear in the non-alpha ToolComponents
    # popover.
    pills = chat_panel.get_tool_pills()
    expect(pills).to_have_count(2)
    expect(pills.nth(0)).to_contain_text("TaskCreate")
    expect(pills.nth(1)).to_contain_text("TaskUpdate")


@user_story("S6: to keep TaskList / TaskGet / TaskOutput / TaskStop out of the chat transcript")
def test_chat_transcript_hides_read_only_task_tools(sculptor_instance_: SculptorInstance) -> None:
    """Read-only TaskList / TaskGet do not surface in the alpha chat transcript.

    Only the user-visible TaskCreate pill should appear; the read-only
    TaskList / TaskGet calls in the same turn are suppressed per
    HIDDEN_TOOL_NAMES.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_HIDDEN_TASK_TOOLS,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    pills = chat_panel.get_tool_pills()
    expect(pills).to_have_count(1)
    expect(pills.first).to_contain_text("TaskCreate")


@user_story("S7: to see a single-task popover with no graph toggle")
def test_single_task_popover_has_no_graph_toggle(sculptor_instance_: SculptorInstance) -> None:
    """A single in-progress task renders one row and no DAG affordances."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_SINGLE_TASK,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("Only task")
    expect(agent_tasks.get_waiting_badges()).to_have_count(0)
    expect(agent_tasks.get_graph_toggle()).to_have_count(0)


@user_story("S2: to see a 'Waiting on' badge + graph toggle when tasks have dependencies")
def test_non_linear_shows_waiting_badge_and_toggle(sculptor_instance_: SculptorInstance) -> None:
    """A non-linear task list (with blockedBy edges) surfaces the badge + toggle.

    The graph itself is empty in Phase 6 — the test asserts only the toggle's
    visibility and the badge text. Phase 7 fills the graph column with SVG.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "A", "status": "completed"}},
    {"command": "task_create", "args": {"id": "2", "subject": "B", "status": "completed", "blockedBy": ["1"]}},
    {"command": "task_create", "args": {"id": "3", "subject": "C", "status": "in_progress", "blockedBy": ["2"]}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(3)

    badges = agent_tasks.get_waiting_badges()
    # Tasks 2 and 3 both have non-empty blockedBy, so two badges.
    expect(badges).to_have_count(2)
    expect(badges.first).to_contain_text("Waiting on #1")

    toggle = agent_tasks.get_graph_toggle()
    expect(toggle).to_be_visible()

    # Toggle is OFF by default → no graph column.
    expect(agent_tasks.get_graph()).to_have_count(0)
    toggle.click()
    expect(agent_tasks.get_graph()).to_have_count(1)


@user_story("S3: to toggle the dependency graph open / closed alongside the list")
def test_graph_toggle_opens_and_closes_graph(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the toggle reveals the SVG dependency graph; clicking again hides it.

    The list stays visible the whole time. Clicking a list row
    while the graph is open expands its detail block but does NOT change the
    graph.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "A", "status": "completed"}},
    {"command": "task_create", "args": {"id": "2", "subject": "B", "status": "completed", "blockedBy": ["1"]}},
    {"command": "task_create", "args": {"id": "3", "subject": "C", "status": "in_progress", "blockedBy": ["2"]}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(3)

    toggle = agent_tasks.get_graph_toggle()
    expect(toggle).to_be_visible()
    expect(agent_tasks.get_graph()).to_have_count(0)

    toggle.click()
    graph = agent_tasks.get_graph()
    expect(graph).to_be_visible()
    nodes = agent_tasks.get_graph_nodes()
    expect(nodes).to_have_count(3)
    # The list stays visible alongside the graph.
    expect(rows).to_have_count(3)

    # Clicking a row while the graph is open expands the row detail and
    # does NOT toggle the graph back off.
    rows.nth(1).click()
    expect(agent_tasks.get_row_details()).to_have_count(1)
    expect(graph).to_be_visible()

    toggle.click()
    expect(agent_tasks.get_graph()).to_have_count(0)
    # List remains.
    expect(rows).to_have_count(3)


@user_story("S5: to inspect a task by clicking its row in the popover")
def test_row_click_expands_inline_detail(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a task row toggles an inline detail block under it.

    Asserts: per-row expansion is independent (multiple rows open at once
    is fine), the detail block carries description + activeForm + Waiting/
    Blocks lines as appropriate, and re-clicking collapses just that row.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "A", "description": "Investigate the bug", "status": "completed", "blocks": ["2"]}},
    {"command": "task_create", "args": {"id": "2", "subject": "B", "description": "Reproduce the failure", "activeForm": "Reproducing the failure", "status": "in_progress", "blockedBy": ["1"], "blocks": ["3", "4"]}},
    {"command": "task_create", "args": {"id": "3", "subject": "C", "description": "Write the fix", "status": "pending", "blockedBy": ["2"]}},
    {"command": "task_create", "args": {"id": "4", "subject": "D", "description": "Add a regression test", "status": "pending", "blockedBy": ["2"]}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(4)

    details = agent_tasks.get_row_details()
    expect(details).to_have_count(0)

    # Click the second row (the in_progress task).
    rows.nth(1).click()
    expect(details).to_have_count(1)
    expanded_second = details.filter(has_text="Reproduce the failure")
    expect(expanded_second).to_be_visible()
    expect(expanded_second).to_contain_text("Reproducing the failure")
    expect(expanded_second).to_contain_text("Waiting on")
    expect(expanded_second).to_contain_text("#1")
    expect(expanded_second).to_contain_text("Blocks")
    expect(expanded_second).to_contain_text("#3")

    # Open a second row — both should stay expanded.
    rows.nth(2).click()
    expect(details).to_have_count(2)
    expanded_third = details.filter(has_text="Write the fix")
    expect(expanded_third).to_be_visible()

    # Re-click the second row → only the third row's detail remains.
    rows.nth(1).click()
    expect(details).to_have_count(1)
    expect(expanded_third).to_be_visible()
    expect(expanded_second).to_have_count(0)


@user_story("a malformed per-task JSON file is tolerated and skipped")
def test_malformed_task_json_is_tolerated(sculptor_instance_: SculptorInstance) -> None:
    """A corrupt task file alongside two valid ones produces a 2-row list.

    Sequence: create two valid tasks; drop a non-JSON file at the corrupt
    task's path; trigger a refresh with another task_update. The backend's
    _read_task_list_artifact should log + skip the corrupt file rather than
    crash, and the panel should render two rows.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Good 1", "status": "in_progress"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Good 2", "status": "pending"}},
    {"command": "write_corrupt_task", "args": {"id": "3"}},
    {"command": "task_update", "args": {"id": "1", "status": "completed"}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(2)


def _bulk_create_prompt(
    *,
    count: int,
    tiers: int,
    in_progress_id: int,
    completed_until: int,
    fan_in_id: int | None = None,
) -> str:
    """Build a multi_step prompt that drives ``count`` tasks into FakeClaude.

    Tasks are distributed evenly into ``tiers`` tiers; each tier-N+1 task depends
    on its same-index counterpart in tier N (single edge). If ``fan_in_id`` is
    provided and lives in tier >= 1, that task instead depends on the first three
    tasks of the previous tier -- enough to trigger the "+K more" waiting badge.
    Status: ids <= ``completed_until`` are completed, ``in_progress_id`` is
    in_progress, and everything else is pending. ``in_progress_id`` takes
    precedence over the completed range.
    """
    tasks_per_tier = count // tiers
    steps: list[dict[str, object]] = []
    for i in range(1, count + 1):
        tier = (i - 1) // tasks_per_tier
        if fan_in_id is not None and i == fan_in_id and tier > 0:
            prev_tier_start = (tier - 1) * tasks_per_tier + 1
            blocked_by = [str(prev_tier_start + k) for k in range(3)]
        else:
            blocked_by = [str(i - tasks_per_tier)] if tier > 0 else []
        if i == in_progress_id:
            status = "in_progress"
        elif i <= completed_until:
            status = "completed"
        else:
            status = "pending"
        steps.append(
            {
                "command": "task_create",
                "args": {
                    "id": str(i),
                    "subject": f"Task {i}",
                    "status": status,
                    "blockedBy": blocked_by,
                },
            }
        )
    payload = json.dumps({"steps": steps})
    return f"fake_claude:multi_step `{payload}`"


@user_story("S4: to keep a 60-task plan readable in the popover")
def test_large_dag_scale_rules(sculptor_instance_: SculptorInstance) -> None:
    """At 60 tasks across 10 tiers, the popover applies three scale rules:

    1. Tasks with > MAX_INLINE_BLOCKED_BY predecessors summarise as "+K more".
    2. The graph view uses compact circle nodes once tasks.length >= 15.
    3. The graph column scrolls vertically when its content overflows.
    """
    page = sculptor_instance_.page

    prompt = _bulk_create_prompt(
        count=60,
        tiers=10,
        in_progress_id=25,
        completed_until=20,
        fan_in_id=31,
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=prompt,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    agent_tasks = PlaywrightAgentTasksPopoverElement(page)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()
    status_pill.click()

    rows = agent_tasks.get_rows()
    expect(rows).to_have_count(60)

    # 1. The fan-in task (id 31, blockedBy=["25","26","27"]) renders "+K more".
    waiting_badges = agent_tasks.get_waiting_badges()
    expect(waiting_badges.first).to_be_visible()
    summarised_badges = waiting_badges.filter(has_text="more")
    expect(summarised_badges.first).to_be_visible()

    # 2. Open the graph view.
    toggle = agent_tasks.get_graph_toggle()
    expect(toggle).to_be_visible()
    toggle.click()

    graph = agent_tasks.get_graph()
    expect(graph).to_be_visible()

    # 5. All 60 nodes are present in the graph.
    graph_nodes = agent_tasks.get_graph_nodes()
    expect(graph_nodes).to_have_count(60)

    # Compact-mode shape inventory (circles vs rects) and vertical-scroll
    # overflow are asserted in AgentTasksGraph.test.tsx — both depend on tasks
    # >= COMPACT_GRAPH_THRESHOLD and on CSS overflow:auto, which the unit
    # tests cover deterministically without page.evaluate.
