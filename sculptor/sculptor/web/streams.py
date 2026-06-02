import time
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from queue import Empty
from queue import Queue
from typing import Generator
from typing import TypeVar
from typing import assert_never
from typing import cast

from fastapi import HTTPException
from loguru import logger
from pydantic import Field
from typeid.errors import TypeIDException

from sculptor.foundation.agents.data_types.ids import AgentMessageID
from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.agents.data_types.ids import TypeIDPrefixMismatchError
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import CompoundEvent
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.state.chat_state import ChatMessage
from sculptor.foundation.state.messages import Message
from sculptor.agents.harness_registry import get_harness_for_config
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Notification
from sculptor.database.models import Project
from sculptor.database.models import TaskID
from sculptor.database.models import UserSettings
from sculptor.database.models import Workspace
from sculptor.interfaces.environments.base import STATE_DIRECTORY
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.btw_service.api import BtwService
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.setup_command_runner import SetupCommandRunner
from sculptor.services.workspace_service.setup_command_runner import SetupOutputChunk
from sculptor.services.workspace_service.setup_command_runner import SetupStateChanged
from sculptor.services.workspace_service.setup_command_runner import TRUNCATION_MARKER
from sculptor.web.auth import UserSession
from sculptor.web.data_types import BtwUpdate
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import UserUpdateSourceTypes
from sculptor.web.data_types import WebviewCommandUiAction
from sculptor.web.data_types import WorkspaceSetupOutputChunk
from sculptor.web.data_types import WorkspaceSetupStatus
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import PrStatusInfo
from sculptor.web.derived import PrStatusInfoCleared
from sculptor.web.derived import TaskUpdate
from sculptor.web.derived import UserUpdate
from sculptor.web.derived import WorkspaceBranchInfo
from sculptor.web.derived import WorkspaceRemoteBranchesInfo
from sculptor.web.derived import create_initial_task_view
from sculptor.web.message_conversion import convert_agent_messages_to_task_update
from sculptor.web.pr_polling_service import PrPollingService
from sculptor.web.repo_polling_manager import manage_workspace_branch_polling
from sculptor.web.ui_actions import add_subscriber as add_ui_action_subscriber
from sculptor.web.ui_actions import remove_subscriber as remove_ui_action_subscriber

StreamUpdateT = TypeVar("StreamUpdateT", bound=StreamingUpdateSourceTypes)

_KEEPALIVE_SECONDS = 10
_POLL_SECONDS = 1

# Synthetic placeholder shown for workspaces whose setup ran under the old
# PTY-based path (pre-runner). The legacy implementation never captured output
# to disk, so there is nothing to replay — but emitting *something* makes it
# clear the run happened and the system did not lose its state.
LEGACY_SETUP_PLACEHOLDER_BYTES = b"(setup ran in a previous Sculptor version; output was not captured)\n"


class ServerStopped(Exception):
    pass


def _forward_setup_state_changed(queue: Queue[StreamingUpdateSourceTypes], event: SetupStateChanged) -> None:
    queue.put_nowait(
        WorkspaceSetupStatus(
            workspace_id=WorkspaceID(event.workspace_id),
            status=event.status,
            run_id=event.run_id,
            exit_code=event.exit_code,
            started_at=event.started_at,
            finished_at=event.finished_at,
            log_truncated=event.log_truncated,
        )
    )


def _forward_setup_output_chunk(queue: Queue[StreamingUpdateSourceTypes], event: SetupOutputChunk) -> None:
    queue.put_nowait(
        WorkspaceSetupOutputChunk(
            workspace_id=WorkspaceID(event.workspace_id),
            run_id=event.run_id,
            seq=event.seq,
            data=event.data,
        )
    )


def _resolve_setup_runner(services: CompleteServiceCollection) -> SetupCommandRunner | None:
    workspace_service = services.workspace_service
    if isinstance(workspace_service, DefaultWorkspaceService):
        return workspace_service.setup_runner
    return None


def _snapshot_setup_state(
    services: CompleteServiceCollection,
    runner: SetupCommandRunner,
) -> list[tuple[WorkspaceSetupStatus, WorkspaceSetupOutputChunk | None]]:
    """Snapshot setup state for the initial stream dump.

    For workspaces with an in-memory runner slot (run started in this process)
    we use the live buffer. For terminal-state workspaces from a previous
    process (e.g. after app restart), we read the persisted log file from
    disk so the SetupStatusCard renders the same content the user saw before
    the restart.
    """
    out: list[tuple[WorkspaceSetupStatus, WorkspaceSetupOutputChunk | None]] = []
    seen_workspace_ids: set[str] = set()
    for state in runner.iter_states():
        if state.status == "not_configured":
            continue
        seen_workspace_ids.add(state.workspace_id)
        ws_id = WorkspaceID(state.workspace_id)
        status = WorkspaceSetupStatus(
            workspace_id=ws_id,
            status=state.status,
            run_id=state.run_id,
            exit_code=state.exit_code,
            started_at=state.started_at,
            finished_at=state.finished_at,
            log_truncated=state.log_truncated,
        )
        chunk: WorkspaceSetupOutputChunk | None = None
        if state.status == "running" and state.run_id is not None:
            run_id, max_seq, head, tail, truncated = runner.get_buffered_output(state.workspace_id)
            payload = head + (TRUNCATION_MARKER if truncated else b"") + tail
            if run_id is not None and payload:
                chunk = WorkspaceSetupOutputChunk(
                    workspace_id=ws_id,
                    run_id=run_id,
                    seq=max_seq,
                    data=payload,
                )
        out.append((status, chunk))

    # Terminal-state workspaces from a previous process: read the persisted
    # log so the card renders without an extra REST round-trip.
    with services.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspaces = list(transaction.get_workspaces())
    for workspace in workspaces:
        if str(workspace.object_id) in seen_workspace_ids:
            continue
        if workspace.is_deleted:
            continue
        if workspace.setup_status not in ("succeeded", "failed", "legacy"):
            continue
        log_bytes: bytes | None = None
        if workspace.setup_log_path and workspace.environment_id:
            log_bytes = _read_persisted_setup_log(workspace.environment_id, workspace.setup_log_path)
        if log_bytes is None:
            # "Migrated" workspaces — those backfilled from the legacy PTY-based
            # setup path — have a terminal status but no captured output.
            # `setup_run_id is None` is the durable signal: the new runner
            # always assigns one. Synthesize a placeholder so the user can
            # see the run happened without thinking the system lost its state.
            if workspace.setup_run_id is None:
                log_bytes = LEGACY_SETUP_PLACEHOLDER_BYTES
            else:
                continue
        ws_id = workspace.object_id
        status = WorkspaceSetupStatus.model_validate(
            {
                "workspace_id": ws_id,
                "status": workspace.setup_status,
                "run_id": workspace.setup_run_id,
                "exit_code": workspace.setup_exit_code,
                "started_at": workspace.setup_started_at,
                "finished_at": workspace.setup_finished_at,
                "log_truncated": workspace.setup_log_truncated,
            }
        )
        chunk = WorkspaceSetupOutputChunk(
            workspace_id=ws_id,
            run_id=workspace.setup_run_id or f"persisted-{workspace.object_id}",
            seq=1,
            data=log_bytes,
        )
        out.append((status, chunk))
    return out


def _read_persisted_setup_log(environment_id: str, relative_log_path: str) -> bytes | None:
    if relative_log_path.startswith("/") or ".." in relative_log_path.split("/"):
        return None
    log_file = Path(environment_id) / STATE_DIRECTORY / relative_log_path
    if not log_file.is_file():
        return None
    try:
        return log_file.read_bytes()
    except OSError as exc:
        logger.error("Failed to read persisted setup log {}: {}", log_file, exc)
        return None


class ScopeAll(SerializableModel):
    pass


class ScopeProject(SerializableModel):
    project_id: ProjectID


class ScopeWorkspace(SerializableModel):
    workspace_id: WorkspaceID
    project_id: ProjectID | None = None


class ScopeAgent(SerializableModel):
    agent_id: TaskID
    workspace_id: WorkspaceID | None = None
    project_id: ProjectID | None = None


Scope = ScopeAll | ScopeProject | ScopeWorkspace | ScopeAgent


def parse_scope_query_param(value: str | None) -> Scope:
    if value is None or value == "":
        return ScopeAll()
    if value == "all":
        return ScopeAll()
    if ":" not in value:
        raise HTTPException(status_code=400, detail=f"invalid scope: '{value}'")
    kind, _, remainder = value.partition(":")
    if kind == "" or remainder == "":
        raise HTTPException(status_code=400, detail=f"invalid scope: '{value}'")
    try:
        if kind == "project":
            return ScopeProject(project_id=ProjectID(remainder))
        if kind == "workspace":
            return ScopeWorkspace(workspace_id=WorkspaceID(remainder))
        if kind == "agent":
            return ScopeAgent(agent_id=TaskID(remainder))
    except (TypeIDException, TypeIDPrefixMismatchError) as e:
        raise HTTPException(status_code=400, detail=f"invalid scope: '{value}'") from e
    raise HTTPException(status_code=400, detail=f"invalid scope: '{value}'")


def resolve_scope(
    scope_values: list[str],
    user_session: UserSession,
    services: CompleteServiceCollection,
) -> Scope:
    """Parse the raw ?scope= query values, authorize the user against the
    referenced entity, and return the resolved (enriched) Scope.

    Pure of FastAPI / WebSocket. The HTTP shim that extracts these arguments
    from a `starlette.websockets.WebSocket` lives in `middleware.py` to
    keep this module free of the cyclic import with middleware.

    Raises HTTPException(400/403/404) so callers wired through FastAPI
    surface the right HTTP status during the upgrade.
    """
    if len(scope_values) > 1:
        raise HTTPException(status_code=400, detail="multiple scope parameters")
    raw = scope_values[0] if scope_values else None
    parsed = parse_scope_query_param(raw)
    if isinstance(parsed, ScopeAll):
        return parsed
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        if isinstance(parsed, ScopeProject):
            project = transaction.get_project(parsed.project_id)
            if project is None or project.is_deleted:
                raise HTTPException(status_code=404, detail=f"project {parsed.project_id} not found")
            if project.organization_reference != user_session.organization_reference:
                raise HTTPException(status_code=403, detail="forbidden")
            return parsed
        if isinstance(parsed, ScopeWorkspace):
            workspace = transaction.get_workspace(parsed.workspace_id)
            if workspace is None or workspace.is_deleted:
                raise HTTPException(status_code=404, detail=f"workspace {parsed.workspace_id} not found")
            if workspace.organization_reference != user_session.organization_reference:
                raise HTTPException(status_code=403, detail="forbidden")
            return parsed.model_copy(update={"project_id": workspace.project_id})
        if isinstance(parsed, ScopeAgent):
            task = services.task_service.get_task(parsed.agent_id, transaction)
            if task is None or task.is_deleted:
                raise HTTPException(status_code=404, detail=f"agent {parsed.agent_id} not found")
            current_state = task.current_state
            if not isinstance(current_state, AgentTaskStateV2):
                raise HTTPException(status_code=404, detail=f"agent {parsed.agent_id} not found")
            if (
                task.user_reference != user_session.user_reference
                or task.organization_reference != user_session.organization_reference
            ):
                raise HTTPException(status_code=403, detail="forbidden")
            workspace_id = current_state.workspace_id
            workspace = transaction.get_workspace(workspace_id)
            if workspace is None or workspace.is_deleted:
                raise HTTPException(status_code=404, detail=f"agent {parsed.agent_id} not found")
            return parsed.model_copy(update={"workspace_id": workspace_id, "project_id": workspace.project_id})
        assert_never(parsed)


class StreamingUpdate(SerializableModel):
    task_update_by_task_id: dict[TaskID, TaskUpdate] = Field(default_factory=dict)
    task_views_by_task_id: dict[TaskID, CodingAgentTaskView] = Field(default_factory=dict)
    user_update: UserUpdate = Field(default_factory=UserUpdate)
    workspace_branch_by_workspace_id: dict[WorkspaceID, WorkspaceBranchInfo | None] = Field(default_factory=dict)
    workspace_remote_branches_by_workspace_id: dict[WorkspaceID, WorkspaceRemoteBranchesInfo | None] = Field(
        default_factory=dict
    )
    pr_status_by_workspace_id: dict[WorkspaceID, PrStatusInfo | None] = Field(default_factory=dict)
    finished_request_ids: tuple[RequestID, ...] = ()
    dependencies_status: DependenciesStatus | None = None
    workspace_setup_status_by_workspace_id: dict[WorkspaceID, WorkspaceSetupStatus] = Field(default_factory=dict)
    workspace_setup_output_by_workspace_id: dict[WorkspaceID, list[WorkspaceSetupOutputChunk]] = Field(
        default_factory=dict
    )
    btw_update: BtwUpdate | None = None
    ui_open_file_by_workspace_id: dict[WorkspaceID, OpenFileUiAction] = Field(default_factory=dict)
    ui_webview_command_by_workspace_id: dict[WorkspaceID, WebviewCommandUiAction] = Field(default_factory=dict)


_WorkspaceValueT = TypeVar("_WorkspaceValueT")


def _narrow_by_workspace_id(
    d: dict[WorkspaceID, _WorkspaceValueT],
    scoped_workspace_ids: frozenset[WorkspaceID],
) -> dict[WorkspaceID, _WorkspaceValueT]:
    """Filter a workspace-id-keyed dict to only entries in the scoped set."""
    return {wid: v for wid, v in d.items() if wid in scoped_workspace_ids}


@dataclass(frozen=True)
class _ScopeProjection:
    """Pre-computed projection state for a non-`all` scope.

    All three narrow scopes reduce to the same shape: a subset of task views
    and a set of in-scope workspace ids. Once you have one of these, building
    the narrowed StreamingUpdate is a single uniform pass — workspace-keyed
    fields run through `_narrow_by_workspace_id`, task-keyed fields filter on
    `view_subset`.
    """

    view_subset: dict[TaskID, CodingAgentTaskView]
    scoped_workspace_ids: frozenset[WorkspaceID]


def _compute_projection(
    update: StreamingUpdate,
    scope: ScopeProject | ScopeWorkspace | ScopeAgent,
    project_workspace_ids: frozenset[WorkspaceID],
) -> _ScopeProjection:
    if isinstance(scope, ScopeProject):
        view_subset: dict[TaskID, CodingAgentTaskView] = {
            tid: v for tid, v in update.task_views_by_task_id.items() if v.project_id == scope.project_id
        }
        return _ScopeProjection(
            view_subset=view_subset,
            scoped_workspace_ids=project_workspace_ids,
        )
    if isinstance(scope, ScopeWorkspace):
        view_subset = {
            tid: v for tid, v in update.task_views_by_task_id.items() if v.workspace_id == scope.workspace_id
        }
        return _ScopeProjection(
            view_subset=view_subset,
            scoped_workspace_ids=frozenset({scope.workspace_id}),
        )
    if isinstance(scope, ScopeAgent):
        view_subset = (
            {scope.agent_id: update.task_views_by_task_id[scope.agent_id]}
            if scope.agent_id in update.task_views_by_task_id
            else {}
        )
        return _ScopeProjection(
            view_subset=view_subset,
            scoped_workspace_ids=frozenset(),
        )
    assert_never(scope)


def project_for_scope(
    update: StreamingUpdate,
    scope: Scope,
    project_workspace_ids: frozenset[WorkspaceID] = frozenset(),
) -> StreamingUpdate:
    """Return a StreamingUpdate narrowed to the data permitted by the scope.

    Pure: no DB / service calls. For ScopeProject, the caller MUST supply
    `project_workspace_ids` — the set of workspace ids belonging to the
    project — since the per-frame update may not contain enough information
    to derive that mapping itself.

    A TaskUpdate without a corresponding entry in task_views_by_task_id (the
    view was sent in a prior frame) is dropped under non-`all` scopes. The
    client rebuilds task state cumulatively, so missing one update for an
    out-of-scope task is the desired outcome.
    """
    if isinstance(scope, ScopeAll):
        return update

    proj = _compute_projection(update, scope, project_workspace_ids)

    return StreamingUpdate(
        task_views_by_task_id=proj.view_subset,
        task_update_by_task_id={
            tid: tu for tid, tu in update.task_update_by_task_id.items() if tid in proj.view_subset
        },
        user_update=UserUpdate(),
        workspace_branch_by_workspace_id=_narrow_by_workspace_id(
            update.workspace_branch_by_workspace_id, proj.scoped_workspace_ids
        ),
        workspace_remote_branches_by_workspace_id=_narrow_by_workspace_id(
            update.workspace_remote_branches_by_workspace_id, proj.scoped_workspace_ids
        ),
        pr_status_by_workspace_id=_narrow_by_workspace_id(update.pr_status_by_workspace_id, proj.scoped_workspace_ids),
        finished_request_ids=(),
        dependencies_status=None,
        workspace_setup_status_by_workspace_id=_narrow_by_workspace_id(
            update.workspace_setup_status_by_workspace_id, proj.scoped_workspace_ids
        ),
        workspace_setup_output_by_workspace_id=_narrow_by_workspace_id(
            update.workspace_setup_output_by_workspace_id, proj.scoped_workspace_ids
        ),
        btw_update=None,
        ui_open_file_by_workspace_id=_narrow_by_workspace_id(
            update.ui_open_file_by_workspace_id, proj.scoped_workspace_ids
        ),
        ui_webview_command_by_workspace_id=_narrow_by_workspace_id(
            update.ui_webview_command_by_workspace_id, proj.scoped_workspace_ids
        ),
    )


def stream_everything(
    user_session: UserSession,
    shutdown_event: ReadOnlyEvent,
    services: CompleteServiceCollection,
    concurrency_group: ConcurrencyGroup,
    scope: Scope = ScopeAll(),
    dependency_management_service: DependencyManagementService | None = None,
    pr_polling_service: PrPollingService | None = None,
    btw_service: BtwService | None = None,
) -> Generator[StreamingUpdate | None, None, None]:
    """Emit unified task/user updates for a user."""
    logger.debug("stream_everything scope: {}", scope)
    # Shut down if either a global or local shutdown is requested.
    combined_event = CompoundEvent([concurrency_group.shutdown_event, shutdown_event])
    project_workspace_ids: set[WorkspaceID] = set()
    if isinstance(scope, ScopeProject):
        with services.data_model_service.open_transaction(RequestID()) as transaction:
            workspaces = transaction.get_workspaces()
        project_workspace_ids = {
            w.object_id for w in workspaces if w.project_id == scope.project_id and not w.is_deleted
        }
    # Scope-conditional wiring. For each scope variant the elif chain below records:
    #
    # - task_subscription_cm: which TaskService subscription to open
    #   (one of subscribe_to_all_tasks_for_user / project / workspace / single).
    # - workspace_branch_workspace_filter, workspace_branch_project_filter:
    #   narrowing args passed into the branch polling manager. None means
    #   "no narrowing — poll everything".
    # - polling_enabled: whether to attach the polling managers at all.
    #   False only for ScopeAgent — project_for_scope drops every workspace-
    #   and project-keyed field for that scope anyway, so polling is pure waste.
    # - attach_full_user_observers: gates the dependency-status observer
    #   AND the dependency_status entry in the initial dump. True only for
    #   ScopeAll, since project_for_scope drops user_update / dependencies_status
    #   for narrower scopes (no client will ever see them).
    # - attach_user_changes_for_close_on_delete: also attaches
    #   data_model_service.observe_user_changes, but solely to feed
    #   entity-deletion events into the close-on-delete check.
    #   True for ScopeProject and ScopeWorkspace. ScopeAgent gets deletion
    #   signals from its single-task subscription instead, so it leaves this
    #   observer detached entirely.
    workspace_branch_workspace_filter: WorkspaceID | None = None
    workspace_branch_project_filter: ProjectID | None = None
    attach_full_user_observers = False
    polling_enabled = False
    attach_user_changes_for_close_on_delete = False
    if isinstance(scope, ScopeAll):
        task_subscription_cm = services.task_service.subscribe_to_all_tasks_for_user(user_session.user_reference)
        attach_full_user_observers = True
        polling_enabled = True
    elif isinstance(scope, ScopeProject):
        task_subscription_cm = services.task_service.subscribe_to_project_task_containers(
            scope.project_id, user_session.user_reference
        )
        workspace_branch_project_filter = scope.project_id
        polling_enabled = True
        attach_user_changes_for_close_on_delete = True
    elif isinstance(scope, ScopeWorkspace):
        task_subscription_cm = services.task_service.subscribe_to_workspace_task_containers(
            scope.workspace_id, user_session.user_reference
        )
        workspace_branch_workspace_filter = scope.workspace_id
        polling_enabled = True
        attach_user_changes_for_close_on_delete = True
    elif isinstance(scope, ScopeAgent):
        task_subscription_cm = services.task_service.subscribe_to_single_task_container(
            scope.agent_id, user_session.user_reference
        )
    else:
        assert_never(scope)
    pr_polling_service_for_notify = pr_polling_service if polling_enabled else None
    register_dependency_observer = attach_full_user_observers and dependency_management_service is not None
    register_pr_observer = polling_enabled and pr_polling_service is not None

    with task_subscription_cm as updates_queue:
        updates_queue_loosely_typed = cast(Queue[StreamingUpdateSourceTypes], updates_queue)
        if register_dependency_observer:
            assert dependency_management_service is not None
            dependency_management_service.add_observer_queue(updates_queue_loosely_typed)
        setup_runner = _resolve_setup_runner(services)
        setup_state_observer = partial(_forward_setup_state_changed, updates_queue_loosely_typed)
        setup_output_observer = partial(_forward_setup_output_chunk, updates_queue_loosely_typed)
        if setup_runner is not None:
            setup_runner.add_state_observer(setup_state_observer)
            setup_runner.add_output_observer(setup_output_observer)
        if register_pr_observer:
            assert pr_polling_service is not None
            pr_polling_service.add_observer(updates_queue_loosely_typed)
        if btw_service:
            btw_service.add_observer_queue(updates_queue_loosely_typed)
        add_ui_action_subscriber(updates_queue_loosely_typed.put_nowait)
        try:
            with ExitStack() as stack:
                if attach_full_user_observers or attach_user_changes_for_close_on_delete:
                    stack.enter_context(
                        services.data_model_service.observe_user_changes(
                            user_reference=user_session.user_reference,
                            organization_reference=user_session.organization_reference,
                            queue=updates_queue_loosely_typed,
                        )
                    )
                workspace_branch_manager = None
                if polling_enabled:
                    workspace_branch_manager = stack.enter_context(
                        manage_workspace_branch_polling(
                            services=services,
                            queue=updates_queue_loosely_typed,
                            concurrency_group=concurrency_group,
                            workspace_filter=workspace_branch_workspace_filter,
                            project_filter=workspace_branch_project_filter,
                        )
                    )
                # Initialize state tracking
                completed_message_by_task_id: dict[TaskID, dict[AgentMessageID, ChatMessage]] = {}
                task_views_by_task_id: dict[TaskID, CodingAgentTaskView] = {}
                task_update_state_by_task_id: dict[TaskID, TaskUpdate] = {}
                pr_poll_last_branch: dict[WorkspaceID, str] = {}

                # Yield the initial state dump
                initial_data: list[StreamingUpdateSourceTypes] = _empty_update_queue(
                    updates_queue=updates_queue_loosely_typed,
                    shutdown_event=combined_event,
                    is_blocking_allowed=False,
                )
                initial_data.append(services.settings)
                if attach_full_user_observers and dependency_management_service is not None:
                    initial_data.append(dependency_management_service.get_status())
                if setup_runner is not None:
                    for state, snapshot_chunk in _snapshot_setup_state(services, setup_runner):
                        initial_data.append(state)
                        if snapshot_chunk is not None:
                            initial_data.append(snapshot_chunk)
                initial_update = StreamingUpdate()
                if initial_data:
                    initial_update = _convert_to_streaming_update(
                        all_data=cast(list[StreamingUpdateSourceTypes | None], initial_data),
                        task_views_by_task_id=task_views_by_task_id,
                        task_update_state_by_task_id=task_update_state_by_task_id,
                        processed_message_by_task_id=completed_message_by_task_id,
                        settings=services.settings,
                    )

                # We yield the initial state before starting the background watchers to minimize time to first message for the frontend
                yield project_for_scope(initial_update, scope, frozenset(project_workspace_ids))

                # Start background watchers after emitting the initial state
                if workspace_branch_manager is not None:
                    workspace_branch_manager.initialize()
                    workspace_branch_manager.update_pollers_based_on_stream(initial_data)
                _notify_pr_polling_service(pr_polling_service_for_notify, initial_data, pr_poll_last_branch)

                # Track last-yielded dependencies status so we only send deltas.
                # The service pushes unconditionally; we filter here per-connection.
                last_yielded_deps_status: DependenciesStatus | None = initial_update.dependencies_status

                # Now continuously yield incremental updates
                while not combined_event.is_set():
                    new_data = _empty_update_queue(
                        updates_queue=updates_queue_loosely_typed,
                        shutdown_event=combined_event,
                        is_blocking_allowed=True,
                    )
                    if workspace_branch_manager is not None:
                        workspace_branch_manager.update_pollers_based_on_stream(new_data)
                    _notify_pr_polling_service(pr_polling_service_for_notify, new_data, pr_poll_last_branch)

                    if isinstance(scope, ScopeProject):
                        for item in new_data:
                            if isinstance(item, CompletedTransaction):
                                for model in item.updated_models:
                                    if not isinstance(model, Workspace):
                                        continue
                                    if model.project_id == scope.project_id and not model.is_deleted:
                                        project_workspace_ids.add(model.object_id)
                                    else:
                                        # Workspace was deleted OR reassigned to a different
                                        # project; either way, drop it from our set so its
                                        # branch / setup-status / pr-status events stop
                                        # leaking into this scope's frames.
                                        project_workspace_ids.discard(model.object_id)

                    if len(new_data) == 0:
                        yield project_for_scope(StreamingUpdate(), scope, frozenset(project_workspace_ids))
                    else:
                        loosely_typed_new_data = cast(list[StreamingUpdateSourceTypes | None], new_data)
                        incremental_update = _convert_to_streaming_update(
                            all_data=loosely_typed_new_data,
                            task_views_by_task_id=task_views_by_task_id,
                            task_update_state_by_task_id=task_update_state_by_task_id,
                            processed_message_by_task_id=completed_message_by_task_id,
                            settings=services.settings,
                        )
                        # Suppress duplicate dependencies status pushes
                        if incremental_update.dependencies_status == last_yielded_deps_status:
                            incremental_update = StreamingUpdate(
                                task_views_by_task_id=incremental_update.task_views_by_task_id,
                                task_update_by_task_id=incremental_update.task_update_by_task_id,
                                user_update=incremental_update.user_update,
                                workspace_branch_by_workspace_id=incremental_update.workspace_branch_by_workspace_id,
                                workspace_remote_branches_by_workspace_id=incremental_update.workspace_remote_branches_by_workspace_id,
                                pr_status_by_workspace_id=incremental_update.pr_status_by_workspace_id,
                                finished_request_ids=incremental_update.finished_request_ids,
                                dependencies_status=None,
                                workspace_setup_status_by_workspace_id=incremental_update.workspace_setup_status_by_workspace_id,
                                workspace_setup_output_by_workspace_id=incremental_update.workspace_setup_output_by_workspace_id,
                                btw_update=incremental_update.btw_update,
                                ui_open_file_by_workspace_id=incremental_update.ui_open_file_by_workspace_id,
                                ui_webview_command_by_workspace_id=incremental_update.ui_webview_command_by_workspace_id,
                            )
                        else:
                            last_yielded_deps_status = incremental_update.dependencies_status
                        yield project_for_scope(incremental_update, scope, frozenset(project_workspace_ids))

                    if _scope_subscribed_entity_was_deleted(scope, new_data):
                        yield None
                        return
        finally:
            if setup_runner is not None:
                setup_runner.remove_state_observer(setup_state_observer)
                setup_runner.remove_output_observer(setup_output_observer)
            if register_dependency_observer:
                assert dependency_management_service is not None
                dependency_management_service.remove_observer_queue(updates_queue_loosely_typed)
            if pr_polling_service is not None:
                pr_polling_service.remove_observer(updates_queue_loosely_typed)
            if btw_service:
                btw_service.remove_observer_queue(updates_queue_loosely_typed)
            remove_ui_action_subscriber(updates_queue_loosely_typed.put_nowait)


def _scope_subscribed_entity_was_deleted(
    scope: Scope,
    data: list[StreamingUpdateSourceTypes],
) -> bool:
    """Return True iff `data` contains a deletion event for `scope`'s entity.

    For ScopeAgent: a TaskMessageContainer carrying the agent task with
    is_deleted=True. For ScopeWorkspace: a CompletedTransaction carrying the
    workspace (or its parent project) with is_deleted=True. For ScopeProject:
    a CompletedTransaction carrying the project with is_deleted=True. For
    ScopeAll: never (single-entity deletion does not close all-scope).
    """
    if isinstance(scope, ScopeAll):
        return False
    if isinstance(scope, ScopeAgent):
        for item in data:
            if isinstance(item, TaskMessageContainer):
                for task in item.tasks:
                    if task.object_id == scope.agent_id and task.is_deleted:
                        return True
        return False
    if isinstance(scope, ScopeWorkspace):
        for item in data:
            if isinstance(item, CompletedTransaction):
                for model in item.updated_models:
                    if isinstance(model, Workspace) and model.object_id == scope.workspace_id and model.is_deleted:
                        return True
                    if (
                        isinstance(model, Project)
                        and scope.project_id is not None
                        and model.object_id == scope.project_id
                        and model.is_deleted
                    ):
                        return True
        return False
    if isinstance(scope, ScopeProject):
        for item in data:
            if isinstance(item, CompletedTransaction):
                for model in item.updated_models:
                    if isinstance(model, Project) and model.object_id == scope.project_id and model.is_deleted:
                        return True
        return False
    assert_never(scope)


def _notify_pr_polling_service(
    pr_polling_service: PrPollingService | None,
    data: list[StreamingUpdateSourceTypes],
    last_branch_by_workspace: dict[WorkspaceID, str],
) -> None:
    """Forward workspace and branch change events to the PR polling service (non-blocking).

    When the *current branch* changes, a ``PrStatusInfoCleared`` sentinel is
    appended directly to *data* so that ``_convert_to_streaming_update``
    includes it in the **same** ``StreamingUpdate`` as the branch change.

    Target branch changes do **not** emit a clearing sentinel — the old PR
    status stays visible until the immediate re-poll replaces it, avoiding
    a visible flash to the "no MR" state.
    """
    if pr_polling_service is None:
        return
    for item in data:
        if isinstance(item, CompletedTransaction):
            for model in item.updated_models:
                if isinstance(model, Workspace):
                    if model.is_deleted:
                        pr_polling_service.on_workspace_deleted(model.object_id)
                    else:
                        pr_polling_service.on_workspace_created(model)
                        # Don't clear PR status on target branch change — the old
                        # status stays visible until the immediate re-poll replaces
                        # it, avoiding a visible flash to the "no MR" state.
        elif isinstance(item, WorkspaceBranchInfo):
            prev = last_branch_by_workspace.get(item.workspace_id)
            last_branch_by_workspace[item.workspace_id] = item.current_branch
            if prev is None:
                # First branch info for this workspace — repo is cloned and
                # git commands work, so it's safe to start PR polling.
                pr_polling_service.on_workspace_ready(item.workspace_id)
            elif prev != item.current_branch:
                pr_polling_service.on_branch_changed(item.workspace_id)
                # Inject the clearing signal into the current batch so the
                # frontend resets PR status in the same message as the branch
                # change, rather than waiting for the next queue drain.
                data.append(PrStatusInfoCleared(workspace_id=item.workspace_id))


def _convert_to_streaming_update(
    all_data: list[StreamingUpdateSourceTypes | None],
    task_views_by_task_id: dict[TaskID, CodingAgentTaskView],
    task_update_state_by_task_id: dict[TaskID, TaskUpdate],
    processed_message_by_task_id: dict[TaskID, dict[AgentMessageID, ChatMessage]],
    settings: SculptorSettings,
) -> StreamingUpdate:
    """Converts a list of source updates into a StreamingUpdate.

    This function processes new data and returns an incremental update containing only changes from this batch.
    It maintains internal state in the passed-in dicts for tracking purposes.
    """
    changed_task_ids: set[TaskID] = set()
    finished_request_ids: list[RequestID] = []
    user_update_sources: list[UserUpdateSourceTypes] = []
    updated_workspace_branch_by_workspace_id: dict[WorkspaceID, WorkspaceBranchInfo | None] = {}
    updated_workspace_remote_branches_by_workspace_id: dict[WorkspaceID, WorkspaceRemoteBranchesInfo | None] = {}
    latest_dependencies_status: DependenciesStatus | None = None
    updated_workspace_setup_status_by_workspace_id: dict[WorkspaceID, WorkspaceSetupStatus] = {}
    updated_workspace_setup_output_by_workspace_id: dict[WorkspaceID, list[WorkspaceSetupOutputChunk]] = {}
    updated_pr_status_by_workspace_id: dict[WorkspaceID, PrStatusInfo | None] = {}
    latest_btw_update: BtwUpdate | None = None
    updated_ui_open_file_by_workspace_id: dict[WorkspaceID, OpenFileUiAction] = {}
    updated_ui_webview_command_by_workspace_id: dict[WorkspaceID, WebviewCommandUiAction] = {}
    messages_by_task: dict[TaskID, list[Message]] = defaultdict(list)

    for model in all_data:
        if model is None:
            continue
        if isinstance(model, TaskMessageContainer):
            _process_task_message_container(
                container=model,
                changed_task_ids=changed_task_ids,
                task_views_by_task_id=task_views_by_task_id,
                messages_by_task=messages_by_task,
                settings=settings,
            )

        elif isinstance(model, CompletedTransaction):
            _process_completed_transaction(
                transaction=model,
                finished_request_ids=finished_request_ids,
                user_update_sources=user_update_sources,
            )

        elif isinstance(model, SculptorSettings):
            user_update_sources.append(model)

        elif isinstance(model, WorkspaceBranchInfo):
            updated_workspace_branch_by_workspace_id[model.workspace_id] = model

        elif isinstance(model, WorkspaceRemoteBranchesInfo):
            updated_workspace_remote_branches_by_workspace_id[model.workspace_id] = model

        elif isinstance(model, DependenciesStatus):
            latest_dependencies_status = model

        elif isinstance(model, WorkspaceSetupStatus):
            updated_workspace_setup_status_by_workspace_id[model.workspace_id] = model

        elif isinstance(model, WorkspaceSetupOutputChunk):
            updated_workspace_setup_output_by_workspace_id.setdefault(model.workspace_id, []).append(model)

        elif isinstance(model, PrStatusInfo):
            updated_pr_status_by_workspace_id[model.workspace_id] = model

        elif isinstance(model, PrStatusInfoCleared):
            updated_pr_status_by_workspace_id[model.workspace_id] = None

        elif isinstance(model, BtwUpdate):
            latest_btw_update = model

        elif isinstance(model, OpenFileUiAction):
            updated_ui_open_file_by_workspace_id[model.workspace_id] = model

        elif isinstance(model, WebviewCommandUiAction):
            updated_ui_webview_command_by_workspace_id[model.workspace_id] = model

        elif isinstance(model, Message):
            raise TypeError("should not have Message models in streaming update")
        else:
            assert_never(model)

    _apply_message_updates_to_task_state(
        messages_by_task=messages_by_task,
        task_update_state_by_task_id=task_update_state_by_task_id,
        processed_message_by_task_id=processed_message_by_task_id,
        task_views_by_task_id=task_views_by_task_id,
    )

    updated_task_views_by_task_id, updated_task_update_by_task_id = _extract_changed_tasks(
        changed_task_ids=changed_task_ids,
        task_views_by_task_id=task_views_by_task_id,
        task_update_state_by_task_id=task_update_state_by_task_id,
    )

    user_update = _convert_to_user_update(all_data=cast(list[UserUpdateSourceTypes | None], user_update_sources))

    return StreamingUpdate(
        task_views_by_task_id=updated_task_views_by_task_id,
        task_update_by_task_id=updated_task_update_by_task_id,
        user_update=user_update,
        workspace_branch_by_workspace_id=updated_workspace_branch_by_workspace_id,
        workspace_remote_branches_by_workspace_id=updated_workspace_remote_branches_by_workspace_id,
        pr_status_by_workspace_id=updated_pr_status_by_workspace_id,
        finished_request_ids=tuple(finished_request_ids),
        dependencies_status=latest_dependencies_status,
        workspace_setup_status_by_workspace_id=updated_workspace_setup_status_by_workspace_id,
        workspace_setup_output_by_workspace_id=updated_workspace_setup_output_by_workspace_id,
        btw_update=latest_btw_update,
        ui_open_file_by_workspace_id=updated_ui_open_file_by_workspace_id,
        ui_webview_command_by_workspace_id=updated_ui_webview_command_by_workspace_id,
    )


def _convert_to_user_update(all_data: list[UserUpdateSourceTypes | None]) -> UserUpdate:
    """Converts a list of models into a UserUpdate."""
    if len(all_data) == 0:
        return UserUpdate()
    notifications: list[Notification] = []
    projects_by_id: dict[ProjectID, Project] = {}
    workspaces_by_id: dict[WorkspaceID, Workspace] = {}
    user_settings = None
    server_settings = None
    for model in all_data:
        match model:
            case None:
                continue
            case CompletedTransaction():
                completed_transaction = model
                for request_model in completed_transaction.updated_models:
                    match request_model:
                        case Notification():
                            notifications.append(request_model)
                        case Project():
                            projects_by_id[request_model.object_id] = request_model
                        case UserSettings():
                            user_settings = request_model
                        case Workspace():
                            workspaces_by_id[request_model.object_id] = request_model
                        case _ as unreachable:
                            assert_never(unreachable)
            case SculptorSettings():
                server_settings = model
            case _ as also_unreachable:
                assert_never(also_unreachable)
    return UserUpdate(
        user_settings=user_settings,
        projects=tuple(projects_by_id.values()),
        workspaces=tuple(workspaces_by_id.values()),
        settings=server_settings,
        notifications=tuple(notifications),
    )


def _process_task_message_container(
    container: TaskMessageContainer,
    changed_task_ids: set[TaskID],
    task_views_by_task_id: dict[TaskID, CodingAgentTaskView],
    messages_by_task: dict[TaskID, list[Message]],
    settings: SculptorSettings,
) -> None:
    for task in container.tasks:
        if not isinstance(task.input_data, AgentTaskInputsV2):
            continue
        changed_task_ids.add(task.object_id)

        if task.object_id not in task_views_by_task_id:
            task_view = create_initial_task_view(task, settings)
            assert isinstance(task_view, CodingAgentTaskView), (
                f"should be impossible: {task=} resulted in non-CodingAgentTaskView view {task_view=} "
            )
            task_views_by_task_id[task.object_id] = task_view
        task_views_by_task_id[task.object_id].update_task(task)

    for message, task_id in container.messages:
        changed_task_ids.add(task_id)
        if task_id in task_views_by_task_id and isinstance(message, Message):
            task_views_by_task_id[task_id].add_message(message)
        messages_by_task[task_id].append(message)


def _process_completed_transaction(
    transaction: CompletedTransaction,
    finished_request_ids: list[RequestID],
    user_update_sources: list[UserUpdateSourceTypes],
) -> None:
    if transaction.request_id is not None:
        finished_request_ids.append(transaction.request_id)
    user_update_sources.append(transaction)


def _apply_message_updates_to_task_state(
    messages_by_task: dict[TaskID, list[Message]],
    task_update_state_by_task_id: dict[TaskID, TaskUpdate],
    processed_message_by_task_id: dict[TaskID, dict[AgentMessageID, ChatMessage]],
    task_views_by_task_id: dict[TaskID, CodingAgentTaskView],
) -> None:
    for task_id, messages in messages_by_task.items():
        # `messages_by_task` carries every task's messages (agent and not), but
        # `task_views_by_task_id` only carries AgentTaskInputsV2 tasks. Non-agent
        # tasks have no harness to resolve.
        task_view = task_views_by_task_id.get(task_id)
        if task_view is None:
            continue
        if task_id not in processed_message_by_task_id:
            processed_message_by_task_id[task_id] = {}

        harness = get_harness_for_config(task_view.task_input.agent_config)
        current_task_update = task_update_state_by_task_id.get(task_id)
        new_task_update = convert_agent_messages_to_task_update(
            new_messages=messages,
            task_id=task_id,
            completed_message_by_id=processed_message_by_task_id[task_id],
            harness=harness,
            current_state=current_task_update,
        )
        task_update_state_by_task_id[task_id] = new_task_update


def _extract_changed_tasks(
    changed_task_ids: set[TaskID],
    task_views_by_task_id: dict[TaskID, CodingAgentTaskView],
    task_update_state_by_task_id: dict[TaskID, TaskUpdate],
) -> tuple[dict[TaskID, CodingAgentTaskView], dict[TaskID, TaskUpdate]]:
    """Extract only the changed tasks from full state to create an incremental update."""
    update_task_views_by_task_id: dict[TaskID, CodingAgentTaskView] = {}
    update_task_update_by_task_id: dict[TaskID, TaskUpdate] = {}

    for task_id in changed_task_ids:
        if task_id in task_views_by_task_id:
            update_task_views_by_task_id[task_id] = task_views_by_task_id[task_id]
        if task_id in task_update_state_by_task_id:
            update_task_update_by_task_id[task_id] = task_update_state_by_task_id[task_id]

    return update_task_views_by_task_id, update_task_update_by_task_id


def _empty_update_queue(
    updates_queue: Queue[StreamUpdateT], shutdown_event: ReadOnlyEvent, is_blocking_allowed: bool
) -> list[StreamUpdateT]:
    """Empties the queue and returns all items in it."""
    all_data: list[StreamUpdateT] = []

    # first get everything that's already in the queue
    while updates_queue.qsize() > 0:
        data = updates_queue.get()
        all_data.append(data)

    # if there was anything at all, we can return it immediately
    if len(all_data) > 0:
        return all_data

    # if we can't block, we're done
    if not is_blocking_allowed:
        return all_data

    # otherwise, if we're allowed to block, we can wait for more data
    start_time = time.monotonic()
    while True:
        try:
            data = updates_queue.get(timeout=_POLL_SECONDS)
        except Empty:
            if shutdown_event.is_set():
                logger.info("Server is stopping, no more updates will be sent.")
                raise ServerStopped("Shutting down because the server is stopping.")
            if time.monotonic() - start_time > _KEEPALIVE_SECONDS:
                return all_data
            else:
                continue
        else:
            # return the rest of it too
            all_data = [data] + _empty_update_queue(
                updates_queue=updates_queue,
                shutdown_event=shutdown_event,
                is_blocking_allowed=False,
            )
            return all_data

    assert False, "This should never be reached, as we either return or raise an exception in the loop above."
