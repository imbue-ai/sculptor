"""Models for Claude Code Workflow-tool progress.

The Workflow tool launches a background task that orchestrates many subagents.
The CLI streams ``system/task_progress`` events whose ``workflow_progress``
payload is a full snapshot of the workflow's state: phase entries and one
entry per subagent. These models mirror that wire format (camelCase via the
SerializableModel alias generator) while tolerating unknown fields and entry
types, since the CLI adds fields across releases.
"""

from typing import Annotated
from typing import Any
from typing import Sequence

from loguru import logger
from pydantic import Field
from pydantic import Tag
from pydantic import ValidationError

from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import build_discriminator

# The task_type the CLI assigns to Workflow-tool background tasks in
# task_started events.
WORKFLOW_TASK_TYPE = "local_workflow"


class WorkflowPhaseProgress(SerializableModel):
    """A phase heading in a workflow's progress tree (wire type ``workflow_phase``)."""

    object_type: str = "WorkflowPhaseProgress"
    index: int = Field(description="Position of this phase in the workflow")
    title: str = Field(default="", description="Phase title from the workflow script's phase() call")
    kind: str = Field(default="", description="Phase kind; 'child' for a nested workflow() group")


class WorkflowAgentProgress(SerializableModel):
    """One subagent's progress in a workflow (wire type ``workflow_agent``)."""

    object_type: str = "WorkflowAgentProgress"
    index: int = Field(description="Position of this agent in the workflow's agent list")
    label: str = Field(default="", description="Display label for the agent")
    phase_index: int | None = Field(default=None, description="Index of the phase this agent belongs to")
    phase_title: str = Field(default="", description="Title of the phase this agent belongs to")
    agent_type: str | None = Field(default=None, description="Custom subagent type, when one is used")
    isolation: str | None = Field(default=None, description="Isolation mode (e.g. 'worktree'), when set")
    model: str = Field(default="", description="Model the agent runs on")
    state: str = Field(
        default="start",
        description="Agent lifecycle state: 'start', 'progress', 'done', or 'error' (new states may appear)",
    )
    queued_at: float | str | None = Field(
        default=None, description="When the agent was queued; presence distinguishes queued from running"
    )
    started_at: float | str | None = Field(
        default=None, description="When the agent actually started; unset while waiting for a slot"
    )
    cached: bool | None = Field(default=None, description="True when the result was replayed from a resume journal")
    prompt_preview: str = Field(default="", description="Truncated prompt the agent was given")
    result_preview: str | None = Field(default=None, description="Truncated final result, once done")
    error: str | None = Field(default=None, description="Error message when state is 'error'")
    tokens: int | None = Field(default=None, description="Tokens the agent has used so far")
    tool_calls: int | None = Field(default=None, description="Number of tool calls the agent has made")
    duration_ms: float | None = Field(default=None, description="Agent run time in milliseconds")
    last_tool_summary: str | None = Field(default=None, description="Summary of the agent's most recent tool call")


WorkflowProgressEntryTypes = Annotated[
    (
        Annotated[WorkflowPhaseProgress, Tag("WorkflowPhaseProgress")]
        | Annotated[WorkflowAgentProgress, Tag("WorkflowAgentProgress")]
    ),
    build_discriminator(),
]


class WorkflowUsage(SerializableModel):
    """Aggregate usage for a workflow run, from ``task_progress.usage``."""

    object_type: str = "WorkflowUsage"
    total_tokens: int | None = Field(default=None, description="Total tokens used across all workflow agents")
    tool_uses: int | None = Field(default=None, description="Total tool calls across all workflow agents")
    duration_ms: float | None = Field(default=None, description="Workflow run time in milliseconds")


class WorkflowTaskState(SerializableModel):
    """Live/last-known state of one Workflow background task.

    Keyed by the launching tool_use_id on TaskUpdate so the frontend can
    correlate it with the Workflow ToolUseBlock in the chat.
    """

    object_type: str = "WorkflowTaskState"
    task_id: str = Field(description="Background task ID assigned by Claude Code")
    tool_use_id: str = Field(description="Tool use ID of the Workflow call that launched the task")
    workflow_name: str = Field(default="", description="Workflow name from the script's meta block")
    status: str = Field(
        default="running",
        description="Task status: 'running' until the CLI reports 'completed', 'failed', or 'stopped'",
    )
    entries: tuple[WorkflowProgressEntryTypes, ...] = Field(
        default=(),
        description="Last seen full progress tree, flat and in wire order; agents reference phases by phase_index",
    )
    usage: WorkflowUsage | None = Field(default=None, description="Aggregate usage across the workflow's agents")
    last_tool_name: str | None = Field(default=None, description="Most recent tool used by any workflow agent")
    summary: str = Field(default="", description="Latest progress or completion summary")


_WIRE_TYPE_TO_ENTRY_MODEL: dict[str, type[WorkflowPhaseProgress] | type[WorkflowAgentProgress]] = {
    "workflow_phase": WorkflowPhaseProgress,
    "workflow_agent": WorkflowAgentProgress,
}


def parse_workflow_progress_entries(
    raw_entries: Sequence[Any] | None,
) -> tuple[WorkflowPhaseProgress | WorkflowAgentProgress, ...] | None:
    """Parse the ``workflow_progress`` list from a task_progress event.

    Returns None when the payload is absent — the CLI omits the tree on pure
    token-tick batches, and absent means "unchanged", not "empty". Callers
    must retain the last seen tree.

    Entries of unknown type (including ``workflow_log``) and entries that fail
    validation are skipped so a malformed or newer-CLI payload never breaks
    the output stream.
    """
    if raw_entries is None:
        return None

    entries: list[WorkflowPhaseProgress | WorkflowAgentProgress] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry_model = _WIRE_TYPE_TO_ENTRY_MODEL.get(raw_entry.get("type", ""))
        if entry_model is None:
            continue
        try:
            entries.append(entry_model.model_validate(raw_entry))
        except ValidationError:
            logger.debug("Skipping malformed workflow progress entry: {}", raw_entry)
    return tuple(entries)
