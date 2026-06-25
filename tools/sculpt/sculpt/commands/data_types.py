"""Pydantic output models for sculpt CLI commands.

Each model defines the JSON shape emitted by a command when ``--json`` is used.
The ``sculpt schema`` subcommand derives JSON Schemas from these models
automatically, so the schema always stays in sync with the actual output.
"""

from pydantic import BaseModel
from pydantic import Field


class WorkspaceCreateOutput(BaseModel):
    """Output of ``sculpt workspace create --json``."""

    id: str = Field(description="Unique workspace ID")
    repo_id: str = Field(description="Associated repo/project ID")
    description: str | None = Field(description="User-provided description")
    strategy: str = Field(description="Workspace initialization strategy (clone, in-place, or worktree)")
    source_branch: str | None = Field(description="Source branch name")


class WorkspaceListItem(BaseModel):
    """Single item in ``sculpt workspace list --json --all``."""

    id: str = Field(description="Unique workspace ID")
    repo_id: str = Field(description="Associated repo/project ID")
    repo_path: str = Field(description="Local filesystem path of the repo")
    description: str | None = Field(description="User-provided description")
    strategy: str = Field(description="Workspace initialization strategy")
    source_branch: str | None = Field(description="Source branch name")
    agent_count: int = Field(description="Number of agents in the workspace")
    is_open: bool = Field(description="Whether the workspace is open")
    created_at: str = Field(description="ISO 8601 datetime of creation")
    last_activity_at: str = Field(description="ISO 8601 datetime of last activity")


class WorkspaceListProjectItem(BaseModel):
    """Single item in ``sculpt workspace list --json`` (per-project, no --all)."""

    id: str = Field(description="Unique workspace ID")
    repo_id: str = Field(description="Associated repo/project ID")
    description: str | None = Field(description="User-provided description")
    strategy: str = Field(description="Workspace initialization strategy")
    source_branch: str | None = Field(description="Source branch the workspace was cut from")
    target_branch: str | None = Field(
        description="Diff/merge target branch (the parent branch for a stacked workspace)"
    )
    requested_branch_name: str | None = Field(description="The workspace's own working branch name")
    is_deleted: bool = Field(description="Whether the workspace has been deleted")


class WorkspaceShowOutput(BaseModel):
    """Output of ``sculpt workspace show --json``."""

    id: str = Field(description="Unique workspace ID")
    repo_id: str = Field(description="Associated repo/project ID")
    repo_path: str = Field(description="Local filesystem path of the repo")
    description: str | None = Field(description="User-provided description")
    strategy: str = Field(description="Workspace initialization strategy")
    source_branch: str | None = Field(description="Source branch name")
    agent_count: int = Field(description="Number of agents in the workspace")
    is_open: bool = Field(description="Whether the workspace is open")
    created_at: str = Field(description="ISO 8601 datetime of creation")
    last_activity_at: str = Field(description="ISO 8601 datetime of last activity")


class WorkspaceRenameOutput(BaseModel):
    """Output of ``sculpt workspace rename --json``."""

    id: str = Field(description="Renamed workspace ID")
    description: str = Field(description="New workspace description")


class WorkspaceDeleteOutput(BaseModel):
    """Output of ``sculpt workspace delete --json``."""

    deleted: bool = Field(description="Always true on success")
    id: str = Field(description="Deleted workspace ID")


class RepoItem(BaseModel):
    """Single item in ``sculpt repo list --json`` / ``sculpt repo show --json``."""

    id: str = Field(description="Unique repo ID")
    name: str = Field(description="Repo display name")
    path: str = Field(description="Local filesystem path")
    accessible: bool = Field(description="Whether the path is accessible")
    created_at: str | None = Field(description="ISO 8601 datetime of creation")


class AgentCreateOutput(BaseModel):
    """Output of ``sculpt agent create --json``."""

    id: str = Field(description="Unique agent ID")
    title: str = Field(description="Agent title")
    status: str = Field(description="Agent infrastructure status")
    model: str = Field(description="LLM model identifier")
    workspace_id: str = Field(description="Parent workspace ID")
    created_at: str = Field(description="ISO 8601 datetime of creation")


class AgentListItem(BaseModel):
    """Single item in ``sculpt agent list --json``."""

    id: str = Field(description="Unique agent ID")
    title: str = Field(description="Agent title")
    status: str = Field(description="Agent infrastructure status")
    model: str | None = Field(description="LLM model identifier (null for terminal agents)")
    workspace_id: str = Field(description="Parent workspace ID")
    created_at: str = Field(description="ISO 8601 datetime of creation")


class AgentShowOutput(BaseModel):
    """Output of ``sculpt agent show --json``."""

    id: str = Field(description="Unique agent ID")
    title: str = Field(description="Agent title")
    status: str = Field(description="Agent infrastructure status")
    model: str | None = Field(description="LLM model identifier (null for terminal agents)")
    interface: str = Field(description="Agent interface type")
    created_at: str = Field(description="ISO 8601 datetime of creation")
    updated_at: str = Field(description="ISO 8601 datetime of last update")
    repo_id: str = Field(description="Associated repo/project ID")
    workspace_id: str = Field(description="Parent workspace ID")
    is_deleted: bool = Field(description="Whether the agent has been deleted")
    artifact_names: list[str] = Field(description="Names of artifacts produced by the agent")
    current_activity: str | None = Field(description="What the agent is currently doing")
    last_activity: str | None = Field(description="Last recorded activity")
    task_completed: int = Field(description="Number of completed tasks")
    task_total: int = Field(description="Total number of tasks")
    current_task_subject: str | None = Field(description="Subject of the in-progress task")
    waiting_detail: str | None = Field(description="Detail about what the agent is waiting for")
    error_detail: str | None = Field(description="Error detail if agent is in error state")


class AgentRenameOutput(BaseModel):
    """Output of ``sculpt agent rename --json``."""

    id: str = Field(description="Renamed agent ID")
    title: str = Field(description="New agent title")


class AgentDeleteOutput(BaseModel):
    """Output of ``sculpt agent delete --json``."""

    deleted: bool = Field(description="Always true on success")
    id: str = Field(description="Deleted agent ID")


class AgentSendOutput(BaseModel):
    """Output of ``sculpt agent send --json``."""

    sent: bool = Field(description="Always true on success")
    agent_id: str = Field(description="Target agent ID")
    message: str = Field(description="Truncated copy of the sent message (max 100 chars)")


class AgentStatusOutput(BaseModel):
    """Output of ``sculpt agent status --json``."""

    id: str = Field(description="Unique agent ID")
    status: str = Field(description="Agent infrastructure status")
    updated_at: str = Field(description="ISO 8601 datetime of last update")
    current_activity: str | None = Field(description="What the agent is currently doing")
    last_activity: str | None = Field(description="Last recorded activity")
    waiting_detail: str | None = Field(description="Detail about what the agent is waiting for")
    error_detail: str | None = Field(description="Error detail if agent is in error state")
    task_completed: int = Field(description="Number of completed tasks")
    task_total: int = Field(description="Total number of tasks")
    current_task_subject: str | None = Field(description="Subject of the in-progress task")


class AgentInterruptOutput(BaseModel):
    """Output of ``sculpt agent interrupt --json``."""

    interrupted: bool = Field(description="Always true on success")
    id: str = Field(description="Interrupted agent ID")


class RunOutput(BaseModel):
    """Output of ``sculpt run --json``."""

    workspace_id: str = Field(description="Created workspace ID")
    agent_id: str = Field(description="Created agent ID")
    strategy: str = Field(description="Workspace initialization strategy")
    model: str = Field(description="LLM model identifier")
    prompt: str = Field(description="The task prompt")


class ErrorOutput(BaseModel):
    """Error output (written to stderr) when a command fails with ``--json``."""

    error: str = Field(description="Error message")
    detail: str = Field(description="Additional detail (may be empty)")
