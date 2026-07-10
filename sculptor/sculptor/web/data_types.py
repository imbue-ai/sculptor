import datetime
from enum import Enum
from enum import StrEnum
from enum import auto
from pathlib import Path
from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import EmailStr
from pydantic import Field
from pydantic import Tag

from sculptor.agents.pi_agent.provider_catalog import ProviderGroup
from sculptor.config.settings import SculptorSettings
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import build_discriminator
from sculptor.foundation.upper_case_str_enum import UpperCaseStrEnum
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.terminal_agent_registry.registry import TerminalAgentRegistration
from sculptor.services.workspace_service.api import GitOperationResult
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.messages import EffortLevel
from sculptor.state.messages import LLMModel
from sculptor.state.messages import Message
from sculptor.state.messages import ModelOption


class TaskInterface(StrEnum):
    TERMINAL = "TERMINAL"
    API = "API"


class AgentTypeName(StrEnum):
    """The per-agent type chosen at creation time.

    `REGISTERED` requires a `registration_id` alongside it.
    """

    CLAUDE = "claude"
    PI = "pi"
    TERMINAL = "terminal"
    REGISTERED = "registered"


class WorkspaceBranchInfo(SerializableModel):
    """Current branch for a workspace's working directory."""

    current_branch: str
    workspace_id: WorkspaceID


class WorkspaceTargetBranchesInfo(SerializableModel):
    """Branches a workspace can target as its merge/diff base.

    These are the repo's remote-tracking branches, or its local branches when
    the repo has no remote, so the selector can still offer merge targets on a
    repo with no remote.
    """

    workspace_id: WorkspaceID
    target_branches: tuple[str, ...]


class PrApproval(SerializableModel):
    """A reviewer's approval status on a pull request."""

    name: str
    approved: bool


class PrComment(SerializableModel):
    """An unresolved comment on a pull request."""

    author: str
    file_path: str
    line: int | None
    body: str


class PrStatusInfo(SerializableModel):
    """PR status information for a workspace, streamed from backend to frontend."""

    workspace_id: WorkspaceID
    pr_state: Literal["none", "open", "merged", "closed"]
    has_conflicts: bool | None = None
    pr_iid: int | None = None
    pr_title: str | None = None
    pr_web_url: str | None = None
    pipeline_status: Literal["running", "passed", "failed"] | None = None
    pipeline_id: int | None = None
    pipeline_web_url: str | None = None
    pipeline_updated_at: str | None = None
    approvals: list[PrApproval] = Field(default_factory=list)
    unresolved_comments: list[PrComment] = Field(default_factory=list)
    error_category: (
        Literal["cli_missing", "not_authenticated", "no_access", "network_error", "rate_limited", "transient"] | None
    ) = None
    error_message: str | None = None
    mismatched_pr_iid: int | None = None
    mismatched_pr_target_branch: str | None = None
    mismatched_pr_web_url: str | None = None


class PrStatusInfoCleared(SerializableModel):
    """Sentinel pushed to the stream to clear a workspace's PR status on the frontend.

    When the workspace branch changes, the old PR status is stale. This signal
    causes the frontend atom to be set to null, showing "Checking PR..." until
    the next poll result arrives.
    """

    workspace_id: WorkspaceID


class RequestModel(SerializableModel):
    pass


class StartTaskRequest(RequestModel):
    prompt: str
    interface: str = TaskInterface.TERMINAL.value
    # Mutually exclusive, one per harness's terms — the same pair as
    # CreateAgentRequest, validated per resolved harness
    # (`_validate_prompt_model_selection`).
    model: LLMModel | None = None
    backend_model: ModelOption | None = None
    files: list[str] = Field(default_factory=list)
    initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.IN_PLACE
    name: str | None = None
    source_branch: str | None = None
    # Mutually exclusive with initialization_strategy.
    # When provided, the task will be created in an existing workspace
    workspace_id: WorkspaceID | None = None
    enter_plan_mode: bool = False
    fast_mode: bool = False
    effort: EffortLevel = EffortLevel.EXTRA_HIGH
    sent_via: str | None = None
    # None means "use the user's most-recently-used harness" (the server
    # resolves it). Prompt-ful creation is always a chat agent; terminal types
    # are rejected (422).
    agent_type: AgentTypeName | None = None


class CreateWorkspaceRequestV2(RequestModel):
    """Create workspace request with project_id in body (not URL)."""

    project_id: str
    initialization_strategy: WorkspaceInitializationStrategy
    source_branch: str | None = None
    description: str | None = None
    # Final branch name after user edits; required for WORKTREE, optional for CLONE, must be None for IN_PLACE.
    requested_branch_name: str | None = None
    # Diff/merge target branch. When None, the backend resolves a sensible default
    # from the repo (origin's default branch, else local main/master).
    target_branch: str | None = None


class UpdateWorkspaceRequest(RequestModel):
    description: str | None = None
    target_branch: str | None = None
    is_open: bool | None = None


class BatchUpdateOpenStateRequest(RequestModel):
    workspace_ids: list[str]
    is_open: bool


class CreateAgentRequest(RequestModel):
    """Create agent request — prompt is optional for the '+' button flow."""

    prompt: str | None = None
    # Mutually exclusive with `backend_model`: a create names its model on
    # exactly one harness's terms — `model` for Claude's static list,
    # `backend_model` (the chosen `ModelOption`) for a backend-sourced catalog
    # (pi). A pi prompt requires `backend_model`; a promptless create must not
    # carry one (post-start selection owns that case).
    model: LLMModel | None = None
    backend_model: ModelOption | None = None
    interface: str = TaskInterface.TERMINAL.value
    files: list[str] = Field(default_factory=list)
    name: str | None = None
    enter_plan_mode: bool = False
    fast_mode: bool = False
    effort: EffortLevel = EffortLevel.EXTRA_HIGH
    sent_via: str | None = None
    # None means "use the user's most-recently-used harness" (the server
    # resolves it, matching the app's "+" button default).
    agent_type: AgentTypeName | None = None
    # Required iff agent_type is REGISTERED.
    registration_id: str | None = None


class RenameAgentRequest(RequestModel):
    title: str


class ListTerminalAgentRegistrationsResponse(SerializableModel):
    """Current terminal-agent registrations (re-read from disk per request)."""

    registrations: list[TerminalAgentRegistration]


class SignalEventRequest(RequestModel):
    """A terminal-agent signal.

    `event` is a plain string so unknown events validate and reach the
    handler (forward compatibility — a closed enum would 422 on additive
    evolution). `session_id` accompanies the `session-id` event only.
    """

    event: str
    session_id: str | None = None


class TerminalInputRequest(RequestModel):
    """An automated prompt for a registered terminal agent.

    Smallest viable surface for v1: text plus whether to submit it — no
    arbitrary key injection.
    """

    text: str
    submit: bool = True


class WorkspaceResponse(SerializableModel):
    object_id: WorkspaceID
    project_id: ProjectID
    description: str
    initialization_strategy: WorkspaceInitializationStrategy
    source_branch: str | None
    target_branch: str | None
    requested_branch_name: str | None
    environment_id: str | None
    # Only meaningful on the streaming path — REST endpoints filter out deleted
    # workspaces via get_workspace(), so they never return is_deleted=True.
    is_deleted: bool
    is_open: bool
    created_at: datetime.datetime
    workspace_setup_command: str | None = None
    setup: "WorkspaceSetupSnapshot | None" = None
    # Absolute path of the workspace's checkout: `<environment_id>/code` for
    # clone/worktree workspaces, the project's local repo path for in-place ones.
    # None when the environment hasn't been initialized yet.
    working_directory: str | None = None
    # Branch currently checked out in that directory, from the workspace
    # service's branch scan cache. None when not yet scanned.
    current_branch: str | None = None


class PreviewBranchNameResponse(SerializableModel):
    """Resolved branch-name preview for the Add Workspace form."""

    branch_name: str


class NewBranchNameValidationResponse(SerializableModel):
    """Validation result for a prospective new workspace branch name.

    `is_valid` is whether the name is a legal git ref (per `git check-ref-format`);
    `already_exists` is whether it collides with an existing local branch. The two
    feed the Add Workspace form's inline branch-name error.
    """

    is_valid: bool
    already_exists: bool


class ProjectEnvVarNames(SerializableModel):
    """Environment variable names loaded from a single project's .sculptor/.env."""

    project_name: str
    project_path: str
    var_names: tuple[str, ...]


class EnvVarNamesResponse(SerializableModel):
    """Environment variable names from the global and per-project .env files."""

    global_var_names: tuple[str, ...]
    global_env_path: str
    projects: tuple[ProjectEnvVarNames, ...]


class AuthenticatedProviderEntry(SerializableModel):
    """One pi provider's catalog metadata annotated with its authentication status."""

    provider_id: str
    display_name: str
    group: ProviderGroup
    in_auth_json: bool
    env_detected: bool
    env_var_names: tuple[str, ...]


class AuthenticatedProvidersResponse(SerializableModel):
    """The full pi provider catalog crossed with current authentication status."""

    providers: tuple[AuthenticatedProviderEntry, ...]


class PiModelsResponse(SerializableModel):
    """The host-side pi catalog for pre-workspace surfaces (the New Workspace modal's picker).

    Mirrors the task-state catalog fields: `available_models` is the curated,
    authenticated-only list and `default_model` is pi's own current model when
    usable. Empty/None means "no usable model" (or a best-effort probe failure),
    driving the same empty state the composer shows.
    """

    available_models: tuple[ModelOption, ...]
    default_model: ModelOption | None


class PiLoginRequest(RequestModel):
    """Start an interactive pi login or logout PTY.

    ``provider_id`` is on-screen guidance / refresh context only — pi's /login and
    /logout take no provider argument (the user selects in pi's own TUI selector).
    """

    mode: Literal["login", "logout"]
    provider_id: str | None = None


class PiLoginResponse(SerializableModel):
    """Identifies the spawned login session; the WS attaches at /pi/login/{id}/ws."""

    login_id: str


class PiLoginStatusResponse(SerializableModel):
    """Whether a login session's credential change has landed in auth.json.

    The modal polls this to auto-close (and refetch) without a manual Done:
    ``completed`` flips true once pi has performed the /login (the provider appeared)
    or /logout (the provider was removed).
    """

    completed: bool


class PasteKeyRequest(RequestModel):
    """Power-user paste-key write for a single-key provider.

    ``key_value`` is stored verbatim in auth.json (a literal key, a ``$ENV``
    reference, or a ``!command``); pi resolves it at read time.
    """

    provider_id: str
    key_value: str


class RecentWorkspaceResponse(SerializableModel):
    """Workspace with denormalized project info and computed fields for cross-project listing."""

    object_id: WorkspaceID
    project_id: ProjectID
    description: str
    initialization_strategy: WorkspaceInitializationStrategy
    source_branch: str | None
    is_deleted: bool
    created_at: datetime.datetime
    project_name: str
    agent_count: int
    is_open: bool
    last_activity_at: datetime.datetime
    # Absolute path of the workspace's checkout: `<environment_id>/code` for
    # clone/worktree workspaces, the project's local repo path for in-place ones.
    # None when the environment hasn't been initialized yet.
    working_directory: str | None = None
    # Branch currently checked out in that directory, from the workspace
    # service's branch scan cache. None when not yet scanned.
    current_branch: str | None = None


class ListWorkspacesResponse(SerializableModel):
    """Response for cross-project workspace listing."""

    workspaces: list[RecentWorkspaceResponse]


class SendMessageRequest(RequestModel):
    message: str
    model: LLMModel
    files: list[str] = Field(default_factory=list)
    enter_plan_mode: bool = False
    exit_plan_mode: bool = False
    fast_mode: bool = False
    effort: EffortLevel = EffortLevel.EXTRA_HIGH
    sent_via: str | None = None


class AnswerQuestionRequest(RequestModel):
    answers: dict[str, str]
    notes: dict[str, str] = Field(default_factory=dict)
    question_data: AskUserQuestionData
    tool_use_id: str
    model: LLMModel


class BtwRequest(RequestModel):
    question: str
    request_id: str


class SetModelRequest(RequestModel):
    # The chosen ModelOption's identity. Sent only for harnesses with a backend
    # model list (pi); the pi adapter issues pi's `set_model` RPC with these.
    provider: str
    model_id: str


class WorkspaceSetupCommandRequest(RequestModel):
    # None resets to the current default; "" means the user explicitly wants no command.
    workspace_setup_command: str | None


class NamingPatternRequest(RequestModel):
    naming_pattern: str


ArtifactDataResponse = Annotated[
    Annotated[TaskListArtifact, Tag("TaskListArtifact")] | Annotated[DiffArtifact, Tag("DiffArtifact")],
    build_discriminator(),
]


class ReadFileRequest(RequestModel):
    file_path: str


class OpenFileUiRequest(RequestModel):
    file_path: str
    mode: Literal["auto", "diff", "file"]


class WebviewNavigateRequest(RequestModel):
    url: str = Field(min_length=1)


class DiscardFileRequest(RequestModel):
    """Request to discard changes for a single file in a workspace."""

    file_path: str


class WorkspaceDiffResponse(SerializableModel):
    """Response containing workspace diff artifact."""

    diff: DiffArtifact | None


class WorkspaceGitOperationResponse(SerializableModel):
    """Response from a workspace git operation."""

    result: GitOperationResult


class CommitFileInfo(SerializableModel):
    """Per-file change info within a single commit."""

    path: str
    status: Literal["M", "A", "D", "R"]
    old_path: str | None = None
    additions: int
    deletions: int


class CommitInfo(SerializableModel):
    """A single commit in the workspace history."""

    hash: str
    short_hash: str
    message: str
    author_name: str
    timestamp: str
    parent_hashes: list[str]
    files: list[CommitFileInfo]


class CommitHistoryResponse(SerializableModel):
    """Response containing commit history for a workspace branch."""

    commits: list[CommitInfo]
    fork_point: str | None


class CommitDiffResponse(SerializableModel):
    """Response containing the unified diff for a single commit."""

    diff: str
    commit_hash: str
    parent_hash: str | None


class WorkspaceFileEntry(SerializableModel):
    """A single file or directory in a workspace's file tree."""

    path: str
    type: Literal["file", "directory"]


class WorkspaceFileListResponse(SerializableModel):
    """Flat list of files and directories in a workspace."""

    files: list[WorkspaceFileEntry]


class OpenInOsRequest(RequestModel):
    """Request to open a file or its containing folder in the OS default application."""

    path: str
    action: Literal["open_file", "open_containing_folder"]


class ReadFileAtRefRequest(RequestModel):
    """Request to read a file's content at a specific git ref."""

    path: str
    git_ref: str


class ReadFileAtRefResponse(SerializableModel):
    """File content at a specific git ref, with encoding metadata."""

    content: str
    encoding: Literal["utf-8", "base64"]


class RepoInfo(SerializableModel):
    """Repository information"""

    repo_path: Path
    current_branch: str
    recent_branches: list[str]
    project_id: ProjectID
    is_github_origin: bool = False
    remote_branches: list[str] = Field(default_factory=list)


class CurrentBranchInfo(SerializableModel):
    """Lightweight repository information with just current branch"""

    current_branch: str


class SkillInfo(SerializableModel):
    """Information about a single Claude Code skill."""

    name: str
    description: str
    source: Literal["custom", "plugin"]
    file_path: str | None = None


class InitializeGitRepoRequest(RequestModel):
    """Request to initialize a directory as a git repository"""

    project_path: str


class CreateInitialCommitRequest(RequestModel):
    """Request to create an initial commit in a new git repository"""

    project_path: str


class ProjectInitializationRequest(RequestModel):
    """Request to initialize a new project"""

    project_path: str


class ConfigStatusResponse(SerializableModel):
    """Response for config status check"""

    has_email: bool
    has_privacy_consent: bool
    has_project: bool
    has_dependencies_passing: bool


class UploadFileResponse(SerializableModel):
    file_id: str


class HealthCheckResponse(SerializableModel):
    version: str
    git_sha: str
    python_version: str
    platform: str
    platform_version: str
    free_disk_gb: float
    min_free_disk_gb: float
    free_disk_gb_warn_limit: float

    uptime_seconds: float
    active_task_count: int
    data_directory: str
    install_mode: str
    install_path: str
    ci_job_id: str | None = None
    ci_ref: str | None = None
    dependencies_status: "DependenciesStatus | None" = None


class UploadDiagnosticsRequest(RequestModel):
    """Request to upload a diagnostics report."""

    description: str
    current_url: str
    frontend_diagnostics: dict[str, str | float | int | None] = Field(default_factory=dict)


class UploadDiagnosticsResponse(SerializableModel):
    """Response after a diagnostics report is uploaded."""

    report_id: str
    s3_url: str


class EmailConfigRequest(RequestModel):
    """Request to save user email configuration"""

    user_email: EmailStr
    full_name: str | None = None
    did_opt_in_to_marketing: bool = False
    is_telemetry_enabled: bool = True


class SkipAccountSetupRequest(RequestModel):
    """Request to complete the onboarding welcome step without an account.

    The user keeps the anonymous, instance-id-based identity; the only choice
    they make on the welcome step is whether telemetry stays on.
    """

    is_telemetry_enabled: bool = True


class SetTelemetryRequest(RequestModel):
    """Toggle the binary telemetry consent."""

    enabled: bool


class UpdateUserConfigRequest(RequestModel):
    """Partial update for ``UserConfig``.

    ``user_config`` is a dict of only the fields the caller wants to change —
    fields absent from the dict are left at their current server-side value.
    The handler merges into the current config and re-validates as a full
    ``UserConfig``. This avoids the lost-update race where a stale
    full-object PUT clobbers fields recently changed by another writer
    (e.g. a debounced panel-layout sync overwriting
    ``enable_in_place_workspaces``).
    """

    user_config: dict[str, Any]


class ExternalApp(str, Enum):
    """Supported external applications for opening paths."""

    VSCODE = "vscode"
    PYCHARM = "pycharm"
    CURSOR = "cursor"
    GHOSTTY = "ghostty"
    ITERM = "iterm"
    TERMINAL = "terminal"
    FINDER = "finder"


class OpenPathInAppRequest(RequestModel):
    """Request to open a file system path in an external application."""

    path: str
    app: ExternalApp


class OpenPathInAppResult(SerializableModel):
    """Result of attempting to open a path in an external application."""

    success: bool
    error_message: str | None = None


class AgentDiagnosticsResponse(SerializableModel):
    """Diagnostics information for a specific agent."""

    session_id: str | None = None
    transcript_file_path: str | None = None
    sculptor_transcript_file_path: str | None = None


class VersionRangeInfo(SerializableModel):
    """Version range configuration for Claude CLI compatibility."""

    min_version: str
    max_version: str
    recommended_version: str


class InstallProgress(SerializableModel):
    """Progress of an ongoing managed binary installation."""

    tool: str
    bytes_downloaded: int
    total_bytes: int | None = None


class BinaryMode(UpperCaseStrEnum):
    MANAGED = auto()
    CUSTOM = auto()


class BinarySource(UpperCaseStrEnum):
    """Where a dependency's active binary was resolved from.

    Distinct from :class:`BinaryMode`, which is the *configured intent*: pi in
    MANAGED mode falls back to a system-PATH binary when no managed copy has
    been downloaded, so its mode can be MANAGED while its source is EXTERNAL.
    """

    MANAGED = auto()
    EXTERNAL = auto()


class DependencyInfo(SerializableModel):
    """Rich status information for a single dependency binary."""

    installed: bool
    path: str | None = None
    version: str | None = None
    is_override: bool = False
    mode: BinaryMode | None = None
    # Where the active binary came from: Sculptor's downloaded, version-pinned
    # copy (MANAGED) or a user-provided one — custom path or system PATH
    # (EXTERNAL). None when not installed, and for tools with no managed mode.
    source: BinarySource | None = None
    version_range: VersionRangeInfo | None = None
    is_version_in_range: bool | None = None
    managed_version: str | None = None
    is_authenticated: bool | None = None
    # Per-tool managed-install state. Carried here (rather than a single
    # top-level field) so a Claude install and a pi install never clobber each
    # other's progress/error.
    install_progress: InstallProgress | None = None
    # Reason this tool's most recent managed install/upgrade failed, if any.
    # Surfaced so the UI can explain a failed update instead of silently showing
    # a stale, out-of-range binary. Cleared when a new install starts or one
    # succeeds.
    install_error: str | None = None


class AuthResult(SerializableModel):
    """Result of a Claude authentication attempt."""

    success: bool
    auth_url: str | None = None
    error: str | None = None


class AuthStartResult(SerializableModel):
    """Result of starting an interactive Claude authentication session.

    Authentication is two steps so it works in headless/remote environments
    (e.g. a container) where the browser-loopback flow can't reach the user's
    browser: start returns the sign-in ``auth_url`` and leaves the CLI running,
    waiting on stdin; the user signs in and pastes the resulting code back via
    :class:`SubmitAuthCodeRequest`.

    On a machine with a usable local browser the CLI completes the loopback flow
    on its own and no code is needed — that case returns ``success=True`` with
    ``needs_code=False``.

    Some tools (e.g. ``gh``) use a browser *device flow* instead: start returns
    ``auth_url`` plus a ``user_code`` for the user to enter at that URL, then the
    CLI polls and completes on its own — no code is pasted back (so ``needs_code``
    stays ``False``); the frontend watches the dependency status for completion.
    """

    auth_url: str | None = None
    needs_code: bool = False
    user_code: str | None = None
    success: bool = False
    error: str | None = None


class SubmitAuthCodeRequest(RequestModel):
    """Submit the code the user pasted from the sign-in page to finish authentication."""

    code: str
    tool: str = "CLAUDE"


class DependenciesStatus(SerializableModel):
    """Status of required dependencies with path/version info."""

    git: DependencyInfo
    claude: DependencyInfo
    pi: DependencyInfo
    gh: DependencyInfo


class RemoteRepo(SerializableModel):
    """A repository listed from GitHub."""

    full_name: str
    clone_url: str
    ssh_url: str
    is_private: bool
    pushed_at: str | None = None
    description: str | None = None


class RemoteCloneRequest(RequestModel):
    """Request to clone a remote repository into a local directory."""

    provider: Literal["github"]
    url: str
    target_dir: str
    name: str
    # When the user picked from the repo list (not the manual-URL form), we
    # also send the `owner/repo` slug. The backend prefers passing this to
    # `gh repo clone`, which then picks the protocol from the user's CLI
    # config rather than forcing the protocol embedded in the URL.
    full_name: str | None = None


class RemoteCloneResponse(SerializableModel):
    """Path of the newly-cloned repository on the backend host."""

    project_path: str


class CloneDefaults(SerializableModel):
    """Backend-owned defaults for the Add Repository → GitHub clone flow.

    ``default_clones_dir`` is the absolute parent dir (``<sculptor_folder>/repos``)
    the dialog pre-fills the Target Folder with. Only the backend knows the real
    sculptor folder, which varies by deployment (dev ``.dev_sculptor``, packaged
    ``~/.sculptor``, hosted ``$SCULPTOR_FOLDER``).
    """

    default_clones_dir: str


class WorkspaceSetupStatus(SerializableModel):
    """Status snapshot for a workspace setup run."""

    workspace_id: WorkspaceID
    status: Literal["not_configured", "pending", "running", "succeeded", "failed", "legacy"]
    run_id: str | None = None
    exit_code: int | None = None
    started_at: float | None = None
    finished_at: float | None = None
    log_truncated: bool = False


class WorkspaceSetupOutputChunk(SerializableModel):
    """Live output chunk for a workspace setup run.

    `data` carries raw output bytes; Pydantic encodes them as base64 over the
    wire and the frontend decodes back to bytes for display.
    """

    workspace_id: WorkspaceID
    run_id: str
    seq: int
    data: bytes


class WorkspaceSetupSnapshot(SerializableModel):
    """Per-workspace setup snapshot embedded in WorkspaceResponse."""

    status: Literal["not_configured", "pending", "running", "succeeded", "failed", "legacy"]
    run_id: str | None = None
    exit_code: int | None = None
    started_at: float | None = None
    finished_at: float | None = None
    log_truncated: bool = False


class BtwUpdate(SerializableModel):
    """Streaming update for a `/btw` side-chat reply."""

    workspace_id: WorkspaceID
    agent_id: TaskID
    request_id: str
    state: Literal["running", "done", "error", "aborted"]
    answer: str
    error_message: str | None = None


class OpenFileUiAction(SerializableModel):
    workspace_id: WorkspaceID
    file_path: str
    mode: Literal["auto", "diff", "file"]


class WebviewCommandUiAction(SerializableModel):
    workspace_id: WorkspaceID
    seq: int
    kind: Literal["navigate", "refresh"]
    url: str | None = None


ExtensionCommandOp = Literal["load", "reload", "unload", "inspect", "list"]


class ExtensionCommandUiAction(SerializableModel):
    """A command broadcast to renderers to act on the extension system.

    Emitted when an agent runs a `sculpt extension` command. ``correlation_id``
    lets each renderer's reply be matched back to the originating CLI request
    (see ``sculptor.web.extension_command_bus``); ``workspace_id`` is the workspace
    the agent's CLI is running in, and routes the action through the same
    per-user WebSocket fan-out as the other UI actions.

    Field meaning by ``op``: ``load`` uses ``source`` (a served manifest URL or
    a remote URL); ``reload``/``unload``/``inspect`` use ``extension_id``;
    ``reload`` may carry ``cache_bust`` to force a fresh fetch; ``list`` ignores
    both and asks for every extension.
    """

    workspace_id: WorkspaceID
    correlation_id: str
    op: ExtensionCommandOp
    extension_id: str | None = None
    source: str | None = None
    cache_bust: str | None = None


class RendererIdentity(SerializableModel):
    """Self-reported identity of a connected renderer (one per page load).

    ``environment`` comes from the renderer's own ``isElectron()`` check, not
    from sniffing the WebSocket handshake. ``origin`` is ``window.location``'s
    origin, which determines the localStorage domain — two renderers on
    different origins can legitimately hold different extension state.

    ``base`` is the bundle's base path within that origin ("/" for the deployed
    app; the OpenHost preview front serves dev bundles under "/proxy/<port>/").
    Origin alone cannot distinguish those windows — sharing an origin is exactly
    what makes the preview setup work — so tooling needs the base to tell a
    preview window from the deployed app. Optional: bundles built before this
    field simply don't report it.
    """

    renderer_id: str
    environment: Literal["electron", "browser"]
    origin: str
    base: str | None = None


class ExtensionRegistrations(SerializableModel):
    """Names-only summary of what an extension registered in a renderer."""

    panels: list[str] = []
    has_settings: bool = False
    overlays: list[str] = []


class ExtensionSnapshot(SerializableModel):
    """A redacted, per-extension view a renderer assembles for ``inspect``/``list``.

    ``config_keys`` lists the persisted setting key names only — never their
    values, which may be credentials (e.g. an extension's API key).
    """

    extension_id: str
    source: str
    status: Literal["loading", "loaded", "error", "disabled", "shadowed", "missing"]
    origin: Literal["dev", "installed", "url", "builtin"]
    error_phase: str | None = None
    error_message: str | None = None
    active_source: str | None = None
    registrations: ExtensionRegistrations | None = None
    config_keys: list[str] = []


class ExtensionCommandResult(SerializableModel):
    """One renderer's reply to an ``ExtensionCommandUiAction``."""

    correlation_id: str
    renderer: RendererIdentity
    op: str
    ok: bool
    error: str | None = None
    extensions: list[ExtensionSnapshot] = []


class ExtensionCommandRequest(SerializableModel):
    """Body for ``POST /api/v1/workspaces/{workspace_id}/extensions/command``."""

    op: ExtensionCommandOp
    extension_id: str | None = None
    source: str | None = None
    cache_bust: str | None = None


class ExtensionCommandResponse(SerializableModel):
    """Aggregated per-renderer replies the command endpoint returns to the CLI."""

    correlation_id: str
    results: list[ExtensionCommandResult] = []


class ExtensionFile(SerializableModel):
    """One file of a packaged extension, base64-encoded for transport."""

    path: str
    content_base64: str


class InstallExtensionRequest(SerializableModel):
    """Body for ``POST /api/v1/workspaces/{workspace_id}/extensions/install``.

    ``persist`` selects the destination: ``False`` (default) writes a dev
    install under the reserved ``dev/<workspace_id>/<extension_id>/`` tree;
    ``True`` writes a permanent install at the top-level ``<extension_id>/``.
    """

    extension_id: str
    files: list[ExtensionFile]
    persist: bool = False


class InstallExtensionResponse(SerializableModel):
    manifest_url: str
    extension_dir: str


# Generic system dependency models for unified frontend rendering


class DirectoryEntry(SerializableModel):
    """A single directory entry returned by the filesystem list endpoint."""

    name: str
    path: str


TaskUpdateTypes = Message | CompletedTransaction
UserUpdateSourceTypes = CompletedTransaction | SculptorSettings
StreamingUpdateSourceTypes = (
    TaskMessageContainer
    | TaskUpdateTypes
    | UserUpdateSourceTypes
    | WorkspaceBranchInfo
    | WorkspaceTargetBranchesInfo
    | DependenciesStatus
    | WorkspaceSetupStatus
    | WorkspaceSetupOutputChunk
    | PrStatusInfo
    | PrStatusInfoCleared
    | BtwUpdate
    | OpenFileUiAction
    | WebviewCommandUiAction
    | ExtensionCommandUiAction
)
