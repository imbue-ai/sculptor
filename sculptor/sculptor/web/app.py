import asyncio
import base64
import contextlib
import json
import logging
import mimetypes
import os
import platform
import queue
import re
import subprocess
import sys
import time
import urllib.parse
from asyncio import CancelledError
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path
from threading import Event
from typing import Any
from typing import Generator
from typing import Iterator
from typing import Literal
from typing import TypeVar
from uuid import uuid4

import anyio
import psutil
import typeid.errors
from fastapi import Depends
from fastapi import File as FastAPIFile
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.websockets import WebSocket
from fastapi.websockets import WebSocketDisconnect
from loguru import logger
from pydantic import ValidationError
from pydantic.alias_generators import to_camel

from sculptor import version
from sculptor.agents.default.claude_code_sdk.btw_process_manager import NoBtwSessionAvailable
from sculptor.agents.harness_registry import get_harness_for_config
from sculptor.common.plugin import get_plugin_dirs
from sculptor.config.settings import SculptorSettings
from sculptor.config.user_config import UserConfig
from sculptor.config.user_config import UserConfigField
from sculptor.constants import ElementIDs
from sculptor.constants import SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.git import is_path_in_git_repo
from sculptor.foundation.git import resolve_worktree_to_main_repo
from sculptor.foundation.log_utils import log_and_exit_program
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import model_dump
from sculptor.foundation.pydantic_utils import model_update
from sculptor.foundation.serialization import SerializedException
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.interfaces.agents.agent import AgentMessageID
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RemoveQueuedMessageUserMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.interfaces.environments.base import ARTIFACTS_DIRECTORY
from sculptor.interfaces.environments.base import STATE_DIRECTORY
from sculptor.interfaces.environments.base import TASKS_SUBDIRECTORY
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TypeIDPrefixMismatchError
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.ids import create_organization_id
from sculptor.primitives.ids import create_user_id
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.data_model_service.data_types import TaskAndDataModelTransaction
from sculptor.services.dependency_management_service import InstallResult
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.git_repo_service.git_commands import run_git_command_local
from sculptor.services.project_service.default_implementation import get_most_recently_used_project_id
from sculptor.services.project_service.default_implementation import update_most_recently_used_project
from sculptor.services.task_service.errors import InvalidTaskOperation
from sculptor.services.task_service.errors import TaskNotFound
from sculptor.services.user_config.telemetry_info import get_onboarding_telemetry_info
from sculptor.services.user_config.telemetry_info import get_telemetry_info as get_telemetry_info_impl
from sculptor.services.user_config.user_config import get_config_path
from sculptor.services.user_config.user_config import get_privacy_settings_for_telemetry
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.user_config.user_config import save_config
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.api import WorkspaceFilesUnavailableError
from sculptor.services.workspace_service.api import WorkspaceNotFoundError
from sculptor.services.workspace_service.api import resolve_workspace_setup_command
from sculptor.services.workspace_service.branch_naming import generate_random_slug
from sculptor.services.workspace_service.branch_naming import resolve_pattern
from sculptor.services.workspace_service.branch_naming import slugify_workspace_name
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.environment_manager.env_file_parser import parse_env_file
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    create_terminal_for_environment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    make_terminal_id,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)
from sculptor.startup_checks import check_is_user_email_field_valid
from sculptor.startup_checks import check_sculptor_directory_writable
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.telemetry import telemetry
from sculptor.utils import build as build_utils
from sculptor.utils.build import get_install_path
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.build import is_packaged
from sculptor.utils.errors import is_irrecoverable_exception
from sculptor.utils.timeout import log_runtime
from sculptor.utils.tracing import ELECTRON_MAIN_PID
from sculptor.utils.tracing import RENDERER_PID
from sculptor.utils.tracing import add_external_events
from sculptor.utils.tracing import is_tracing_enabled
from sculptor.web.access_log_filter import should_suppress_access_log
from sculptor.web.auth import SESSION_TOKEN_HEADER_NAME
from sculptor.web.auth import SessionTokenMiddleware
from sculptor.web.auth import UserSession
from sculptor.web.data_types import AgentDiagnosticsResponse
from sculptor.web.data_types import AnswerQuestionRequest
from sculptor.web.data_types import ArtifactDataResponse
from sculptor.web.data_types import AuthResult
from sculptor.web.data_types import BatchUpdateOpenStateRequest
from sculptor.web.data_types import BranchExistsResponse
from sculptor.web.data_types import BtwRequest
from sculptor.web.data_types import CommitDiffResponse
from sculptor.web.data_types import CommitFileInfo
from sculptor.web.data_types import CommitHistoryResponse
from sculptor.web.data_types import CommitInfo
from sculptor.web.data_types import ConfigStatusResponse
from sculptor.web.data_types import CreateAgentRequest
from sculptor.web.data_types import CreateInitialCommitRequest
from sculptor.web.data_types import CreateWorkspaceRequestV2
from sculptor.web.data_types import CurrentBranchInfo
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import DirectoryEntry
from sculptor.web.data_types import DiscardFileRequest
from sculptor.web.data_types import EmailConfigRequest
from sculptor.web.data_types import EnvVarNamesResponse
from sculptor.web.data_types import HealthCheckResponse
from sculptor.web.data_types import InitializeGitRepoRequest
from sculptor.web.data_types import ListWorkspacesResponse
from sculptor.web.data_types import NamingPatternRequest
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.data_types import OpenFileUiRequest
from sculptor.web.data_types import OpenInOsRequest
from sculptor.web.data_types import OpenPathInAppRequest
from sculptor.web.data_types import OpenPathInAppResult
from sculptor.web.data_types import PreviewBranchNameResponse
from sculptor.web.data_types import ProjectEnvVarNames
from sculptor.web.data_types import ProjectInitializationRequest
from sculptor.web.data_types import ReadFileAtRefRequest
from sculptor.web.data_types import ReadFileAtRefResponse
from sculptor.web.data_types import ReadFileRequest
from sculptor.web.data_types import RecentWorkspaceResponse
from sculptor.web.data_types import RenameAgentRequest
from sculptor.web.data_types import RepoInfo
from sculptor.web.data_types import SendMessageRequest
from sculptor.web.data_types import SetTelemetryRequest
from sculptor.web.data_types import SkillInfo
from sculptor.web.data_types import SkipAccountSetupRequest
from sculptor.web.data_types import StartTaskRequest
from sculptor.web.data_types import UpdateUserConfigRequest
from sculptor.web.data_types import UpdateWorkspaceRequest
from sculptor.web.data_types import UploadDiagnosticsRequest
from sculptor.web.data_types import UploadDiagnosticsResponse
from sculptor.web.data_types import UploadFileResponse
from sculptor.web.data_types import WebviewCommandUiAction
from sculptor.web.data_types import WebviewNavigateRequest
from sculptor.web.data_types import WorkspaceDiffResponse
from sculptor.web.data_types import WorkspaceFileEntry
from sculptor.web.data_types import WorkspaceFileListResponse
from sculptor.web.data_types import WorkspaceGitOperationResponse
from sculptor.web.data_types import WorkspaceResponse
from sculptor.web.data_types import WorkspaceSetupCommandRequest
from sculptor.web.data_types import WorkspaceSetupSnapshot
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import TaskInterface
from sculptor.web.derived import TaskViewTypes
from sculptor.web.derived import create_initial_task_view
from sculptor.web.message_conversion import convert_agent_messages_to_task_update
from sculptor.web.middleware import App
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_root_concurrency_group
from sculptor.web.middleware import get_services_from_request_or_websocket
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import get_user_session
from sculptor.web.middleware import get_user_session_for_websocket
from sculptor.web.middleware import lifespan
from sculptor.web.middleware import register_on_startup
from sculptor.web.middleware import resolve_stream_scope
from sculptor.web.middleware import run_sync_function_with_debugging_support_if_enabled
from sculptor.web.middleware import shutdown_event as shutdown_event_impl
from sculptor.web.open_with import open_path_in_external_app
from sculptor.web.skills import discover_skills
from sculptor.web.streams import Scope
from sculptor.web.streams import ServerStopped
from sculptor.web.streams import StreamingUpdate
from sculptor.web.streams import stream_everything
from sculptor.web.ui_actions import next_webview_seq
from sculptor.web.ui_actions import publish_ui_action
from sculptor.web.upload_diagnostics import upload_diagnostics as perform_upload_diagnostics

UpdateT = TypeVar("UpdateT", bound=StreamingUpdate)

_SERVER_START_TIME = time.time()


def validate_project_id(project_id: str) -> ProjectID:
    """Validate and return a ProjectID, raising HTTPException if invalid."""
    try:
        return ProjectID(project_id)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["path", "project_id"],
                    "msg": f"Invalid project ID format: {project_id}",
                    "type": "value_error",
                }
            ],
        ) from e


def validate_task_id(task_id: str) -> TaskID:
    """Validate and return a TaskID, raising HTTPException if invalid."""
    try:
        return TaskID(task_id)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["path", "task_id"], "msg": f"Invalid task ID format: {task_id}", "type": "value_error"}],
        ) from e


def validate_workspace_id(workspace_id: str) -> WorkspaceID:
    """Validate and return a WorkspaceID, raising HTTPException if invalid."""
    try:
        return WorkspaceID(workspace_id)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["path", "workspace_id"],
                    "msg": f"Invalid workspace ID format: {workspace_id}",
                    "type": "value_error",
                }
            ],
        ) from e


def _workspace_to_response(workspace: Workspace, workspace_setup_command: str | None = None) -> WorkspaceResponse:
    """Convert a Workspace model to a WorkspaceResponse."""
    setup_snapshot = _build_setup_snapshot(workspace)
    return WorkspaceResponse(
        object_id=workspace.object_id,
        project_id=workspace.project_id,
        description=workspace.description,
        initialization_strategy=workspace.initialization_strategy,
        source_branch=workspace.source_branch,
        target_branch=workspace.target_branch,
        requested_branch_name=workspace.requested_branch_name,
        environment_id=workspace.environment_id,
        is_deleted=workspace.is_deleted,
        is_open=workspace.is_open,
        created_at=workspace.created_at,
        workspace_setup_command=workspace_setup_command,
        setup=setup_snapshot,
    )


for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Check for shutdown message
        if "Shutting down" in record.getMessage():
            print("\nAttempting shutdown and cleaning up. Please wait this can take a moment ...")

        if record.exc_info and record.exc_info[0] is KeyboardInterrupt:
            logger.debug("Keyboard interrupt received")
            return

        if "BrokenPipeError: [Errno 32] Broken pipe" in record.getMessage():
            level = "WARNING"

        # Suppress access logs for frequently polled routes to reduce log noise
        if record.name == "uvicorn.access":
            if should_suppress_access_log(record.getMessage()):
                return

        # Find caller to get correct stack depth
        frame, depth = logging.currentframe(), 2
        while frame.f_back and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# Replace handlers for specific loggers
logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)

loggers = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "fastapi",
    "asyncio",
    "starlette",
)

for logger_name in loggers:
    logging_logger = logging.getLogger(logger_name)
    logging_logger.handlers = []
    logging_logger.propagate = True


APP = App(title="Sculptor V1 API", lifespan=lifespan)

NUM_WORKER_THREADS = 40


def on_startup():
    # Based on https://github.com/Kludex/starlette/issues/1724#issuecomment-1717476987
    # Which I found from https://github.com/fastapi/fastapi/discussions/4593
    # Also looked at https://github.com/fastapi/fastapi/issues/4221 but that appears to be out of date; Does not work.

    # This is where+how we can set the number of worker threads in the app's underlying pool.
    # I found this to verify the number of workers we actually have (defaults to 40)
    # and ensure that we're not going to run out under load from long-running requests.
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = NUM_WORKER_THREADS

    # Verify that the Sculptor data directory is writable
    if not check_sculptor_directory_writable():
        logger.error("Sculptor cannot start: data directory is not writable")
        raise RuntimeError("Sculptor data directory is not writable. Please check permissions.")


register_on_startup(on_startup)


## Cors section. This should be the only place the backend process cares about SCULPTOR_FRONTEND_PORT
frontend_port = os.environ.get("SCULPTOR_FRONTEND_PORT", 5173)
frontend_host = os.environ.get("SCULPTOR_FRONTEND_HOST", None)
api_port = os.environ.get("SCULPTOR_API_PORT", 5050)

is_integration_testing = os.environ.get("TESTING__INTEGRATION_ENABLED", "false").lower() == "true"


# Add CORS middleware to allow requests from file:// origins and localhost
APP.add_middleware(
    # pyre doesn't understand the typing here
    CORSMiddleware,  # pyre-ignore[6]
    allow_origins=[
        f"http://localhost:{frontend_port}",  # Vite dev server
        f"http://127.0.0.1:{frontend_port}",  # Vite dev server
        f"http://localhost:{api_port}",  # Direct web backend access, this usually doesnt need cors
        f"http://127.0.0.1:{api_port}",  # Direct web backend access, this usually doesnt need cors
        *([f"http://{frontend_host}:{frontend_port}"] if frontend_host is not None else []),
        "null",  # file:// URLs report origin as "null"
    ],
    # If we are running for an integration test, we need to allow any port so that our clients can port-hop.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if is_integration_testing else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@APP.exception_handler(Exception)
async def irrecoverable_exception_handler(request: Request, exception: Exception) -> None:
    if is_irrecoverable_exception(exception):
        logger.opt(exception=exception).info(
            "Irrecoverable exception encountered. Terminating the program immediately."
        )
        log_and_exit_program(
            SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR, "Irrecoverable exception encountered (see logs for details)."
        )
    raise exception


# Add GZip middleware for compression
# pyre-ignore[6]:
# The signature for middleware classes defined by Starlette (_MiddlewareFactory.__call__) is wrong.
APP.add_middleware(GZipMiddleware, minimum_size=1000)

router = DecoratedAPIRouter(decorator=add_logging_context)


@router.get("/api/v1/session-token", status_code=204)
def set_session_token_cookie(
    response: Response,
    settings: SculptorSettings = Depends(get_settings),
) -> None:
    response.set_cookie(
        key=SESSION_TOKEN_HEADER_NAME,
        value=settings.SESSION_TOKEN or "",
        samesite="strict",
        httponly=True,
    )


@router.post("/api/v1/projects/{project_id}/tasks")
def start_task(
    project_id: ProjectID,
    request: Request,
    task_request: StartTaskRequest,
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> CodingAgentTaskView:
    """Start a new task with the given prompt"""
    prompt = task_request.prompt
    interface = task_request.interface
    model = task_request.model
    initialization_strategy = task_request.initialization_strategy
    task_name = task_request.name
    source_branch = task_request.source_branch
    workspace_id = task_request.workspace_id
    task_id = TaskID()

    with logger.contextualize(task_id=task_id), log_runtime("start_task"):
        if not prompt:
            logger.error("Start task request without prompt")
            raise HTTPException(
                status_code=422,
                detail=[{"loc": ["body", "prompt"], "msg": "Prompt is required", "type": "value_error.missing"}],
            )

        services = get_services_from_request_or_websocket(request)
        _prevent_action_if_out_of_free_space(services)

        try:
            interface = TaskInterface(interface)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid interface: {interface}. Must be 'terminal' or 'api'",
            ) from e

        logger.info(
            "Starting new task with interface {} and initialization_strategy {}", interface, initialization_strategy
        )

        if model in (LLMModel.FAKE_CLAUDE, LLMModel.FAKE_CLAUDE_2) and not settings.TESTING.INTEGRATION_ENABLED:
            raise HTTPException(
                status_code=422,
                detail="Testing model is only available when integration testing is enabled",
            )

        # little transaction here -- we don't want to span the whole thing bc then it will be slow
        with user_session.open_transaction(services) as transaction:
            project = transaction.get_project(project_id)
            assert project is not None, f"Project {project_id} not found"

            if workspace_id is not None:
                # Use existing workspace
                workspace = transaction.get_workspace(workspace_id)
                if workspace is None or workspace.is_deleted:
                    raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
                if workspace.project_id != project_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Workspace {workspace_id} belongs to a different project",
                    )
                logger.debug("Using existing workspace {} for task {}", workspace.object_id, task_id)
            else:
                # Create implicit workspace for this task
                workspace = services.workspace_service.create_workspace(
                    project=project,
                    initialization_strategy=initialization_strategy,
                    source_branch=source_branch,
                    requested_branch_name=None,
                    description=task_name,
                    transaction=transaction,
                )
                logger.debug("Created workspace {} for task {}", workspace.object_id, task_id)

            # Auto-assign "Agent N" name when no explicit name is provided
            if not task_name:
                workspace_tasks = _get_tasks_for_workspace(workspace, transaction)
                task_name = _compute_next_agent_name(workspace_tasks)

        agent_config = _agent_config_for_workspace(workspace)

        with services.git_repo_service.open_local_user_git_repo_for_read(project) as repo:
            # Get the current commit hash to use as the starting point for diffs
            initial_commit_hash = repo.get_current_commit_hash()

        max_seconds = None

        # Create initial task state with workspace_id
        initial_task_state = AgentTaskStateV2(
            title=task_name,
            workspace_id=workspace.object_id,
        )

        task = Task(
            object_id=task_id,
            max_seconds=max_seconds,
            organization_reference=user_session.organization_reference,
            user_reference=user_session.user_reference,
            project_id=project.object_id,
            input_data=AgentTaskInputsV2(
                agent_config=agent_config,
                git_hash=initial_commit_hash,
                system_prompt=project.default_system_prompt,
                default_model=model,
            ),
            current_state=initial_task_state,
        )

        logger.debug("Creating root concurrency group and opening transaction.")
        root_concurrency_group = get_root_concurrency_group(request)
        with (
            root_concurrency_group.make_concurrency_group(name="start_task") as _concurrency_group,
            user_session.open_transaction(services) as transaction,
        ):
            logger.debug("Creating task and inserting it into the database.")
            inserted_task = services.task_service.create_task(task, transaction)
            task_id = inserted_task.object_id

            logger.debug("Creating initial messages...")
            messages = []
            input_user_message = ChatInputUserMessage(
                text=prompt,
                message_id=AgentMessageID(),
                model_name=model,
                files=task_request.files,
                enter_plan_mode=task_request.enter_plan_mode,
                fast_mode=task_request.fast_mode,
                effort=task_request.effort,
                sent_via=task_request.sent_via,
            )
            messages.append(input_user_message)
            services.task_service.create_message(
                message=input_user_message,
                task_id=task_id,
                transaction=transaction,
            )

        logger.debug("Creating initial task view.")
        task_view = create_initial_task_view(task, settings)
        assert isinstance(task_view, CodingAgentTaskView)
        logger.debug("Adding messages to task view.")
        for message in messages:
            task_view.add_message(message)
        logger.debug("Done adding messages to task view.")
        return task_view


def _cleanup_task_file_attachments(
    task_id: TaskID,
    services: CompleteServiceCollection,
    transaction: DataModelTransaction,
) -> None:
    """Clean up files associated with a task.

    Collects all file paths from ChatInputUserMessage messages and deletes them from disk.
    """
    messages = services.task_service.get_saved_messages_for_task(task_id, transaction)
    file_paths: set[str] = set()

    for message in messages:
        if isinstance(message, ChatInputUserMessage) and message.files:
            file_paths.update(message.files)

    if not file_paths:
        return

    for file_path in file_paths:
        try:
            file_file = Path(file_path)
            if file_file.exists():
                file_file.unlink()
                logger.debug("Deleted file: {}", file_path)
        except Exception as e:
            log_exception(e, "Failed to delete {file_path}", file_path=file_path)
    logger.info("Cleaned up {} file(s) for task {}", len(file_paths), task_id)


# =====================
# Workspace Endpoints
# =====================


@router.post("/api/v1/workspaces")
def create_workspace_v2(
    request: Request,
    workspace_request: CreateWorkspaceRequestV2,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceResponse:
    """Create a new workspace with project_id in the request body."""
    validated_project_id = validate_project_id(workspace_request.project_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(validated_project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {workspace_request.project_id} not found")

        strategy = workspace_request.initialization_strategy
        branch_name = workspace_request.requested_branch_name
        if strategy == WorkspaceInitializationStrategy.IN_PLACE:
            if branch_name is not None:
                raise HTTPException(
                    status_code=400,
                    detail="requested_branch_name is not supported for IN_PLACE workspaces",
                )
        elif strategy == WorkspaceInitializationStrategy.WORKTREE:
            if branch_name is None or not branch_name.strip():
                raise HTTPException(
                    status_code=400, detail="requested_branch_name is required for WORKTREE workspaces"
                )
            if workspace_request.source_branch is None:
                raise HTTPException(status_code=400, detail="source_branch is required for WORKTREE workspaces")

        if branch_name:
            with services.git_repo_service.open_local_user_git_repo_for_read(project, log_command=False) as repo:
                if repo.is_branch_ref(branch_name):
                    raise HTTPException(status_code=409, detail=f"Branch '{branch_name}' already exists")

        workspace = services.workspace_service.create_workspace(
            project=project,
            initialization_strategy=workspace_request.initialization_strategy,
            source_branch=workspace_request.source_branch,
            requested_branch_name=branch_name,
            description=workspace_request.description,
            transaction=transaction,
            target_branch=workspace_request.target_branch,
            harness=workspace_request.harness,
        )
        update_most_recently_used_project(project_id=validated_project_id)
        logger.info("Created workspace {} for project {}", workspace.object_id, workspace_request.project_id)
        setup_command = (
            resolve_workspace_setup_command(project.workspace_setup_command)
            if workspace.initialization_strategy
            in (WorkspaceInitializationStrategy.CLONE, WorkspaceInitializationStrategy.WORKTREE)
            else None
        )
        return _workspace_to_response(workspace, workspace_setup_command=setup_command)


_PREVIEW_BRANCH_NAME_GIT_TIMEOUT = 5.0


@router.get("/api/v1/workspaces/preview-branch-name")
def preview_branch_name(
    request: Request,
    project_id: str,
    workspace_name: str = "",
    mode: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.WORKTREE,
    user_session: UserSession = Depends(get_user_session),
) -> PreviewBranchNameResponse:
    """Resolve the auto-filled branch-name preview for the Add Workspace form.

    In-place mode returns an empty string since the field is hidden. Clone and
    worktree modes resolve the project's or user-global naming pattern against
    a `<slug>` derived from the workspace name (random if empty) and a `<user>`
    slug derived from the repo's `git config user.name`.
    """
    if mode == WorkspaceInitializationStrategy.IN_PLACE:
        return PreviewBranchNameResponse(branch_name="")

    validated_project_id = validate_project_id(project_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(validated_project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if project.naming_pattern is not None and project.naming_pattern.strip():
        pattern = project.naming_pattern
    else:
        user_config = get_user_config_instance()
        pattern = user_config.default_workspace_branch_naming_pattern if user_config is not None else "<user>/<slug>"

    name_slug = slugify_workspace_name(workspace_name)
    if not name_slug:
        name_slug = generate_random_slug()

    full_name = ""
    root_concurrency_group = get_root_concurrency_group(request)
    with root_concurrency_group.make_concurrency_group(name="preview_branch_name") as cg:
        try:
            returncode, stdout, _ = run_git_command_local(
                cg,
                ["git", "config", "user.name"],
                cwd=project.get_local_user_path(),
                check_output=False,
                timeout=_PREVIEW_BRANCH_NAME_GIT_TIMEOUT,
                is_retry_safe=True,
            )
            if returncode == 0:
                full_name = stdout.strip()
        except Exception:
            full_name = ""
    first_token = full_name.split()[0] if full_name else ""
    user_slug = slugify_workspace_name(first_token) if first_token else ""

    resolved = resolve_pattern(pattern, user_slug=user_slug, name_slug=name_slug)
    return PreviewBranchNameResponse(branch_name=resolved)


def _build_setup_snapshot(workspace: Workspace) -> WorkspaceSetupSnapshot:
    return WorkspaceSetupSnapshot.model_validate(
        {
            "status": workspace.setup_status,
            "run_id": workspace.setup_run_id,
            "exit_code": workspace.setup_exit_code,
            "started_at": workspace.setup_started_at,
            "finished_at": workspace.setup_finished_at,
            "log_truncated": workspace.setup_log_truncated,
        }
    )


@router.post("/api/v1/workspaces/{workspace_id}/setup/cancel")
def cancel_workspace_setup(
    request: Request,
    workspace_id: str,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceSetupSnapshot:
    services = get_services_from_request_or_websocket(request)
    workspace_service = services.workspace_service
    if not isinstance(workspace_service, DefaultWorkspaceService):
        raise HTTPException(status_code=500, detail="Workspace service does not support setup runner")
    runner = workspace_service.setup_runner
    if not runner.cancel(workspace_id):
        raise HTTPException(status_code=409, detail={"error": "not running"})
    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(WorkspaceID(workspace_id))
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return _build_setup_snapshot(workspace)


@router.post("/api/v1/workspaces/{workspace_id}/setup/rerun")
def rerun_workspace_setup(
    request: Request,
    workspace_id: str,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceSetupSnapshot:
    services = get_services_from_request_or_websocket(request)
    workspace_service = services.workspace_service
    if not isinstance(workspace_service, DefaultWorkspaceService):
        raise HTTPException(status_code=500, detail="Workspace service does not support setup runner")
    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(WorkspaceID(workspace_id))
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail="Workspace not found")
        project = transaction.get_project(workspace.project_id)
        environment_id = workspace.environment_id
        project_path = project.get_local_user_path() if project is not None else None
        project_id = project.object_id if project is not None else None
        initialization_strategy = workspace.initialization_strategy
        # Resolve through the project's tri-state default helper so a `None`
        # stored value runs the current default and `""` (user-cleared) blocks.
        command = resolve_workspace_setup_command(project.workspace_setup_command) if project is not None else None
    if command is None or not command.strip():
        raise HTTPException(status_code=422, detail={"error": "no setup command configured"})
    if environment_id is None or project_id is None or project_path is None:
        raise HTTPException(status_code=409, detail={"error": "environment not ready"})
    if workspace_service.setup_runner.get_state(workspace_id) is not None:
        existing = workspace_service.setup_runner.get_state(workspace_id)
        if existing is not None and existing.status == "running":
            raise HTTPException(status_code=409, detail={"error": "setup already running"})
    environment = workspace_service.environment_manager.resume_environment(
        environment_id=environment_id,
        project_path=project_path,
        project_id=project_id,
        concurrency_group=workspace_service.concurrency_group,
        initialization_strategy=initialization_strategy,
    )
    state_dir = environment.to_host_path(environment.get_state_path())
    workspace_service.setup_runner.start(
        workspace_id=workspace_id,
        command=command,
        subprocess_runner=environment.run_setup_subprocess,
        shutdown_event_source=environment.concurrency_group.shutdown_event,
        state_dir=state_dir,
        on_persist=workspace_service._persist_setup_state,
    )
    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(WorkspaceID(workspace_id))
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return _build_setup_snapshot(workspace)


@router.get("/api/v1/workspaces/recent")
def list_recent_workspaces(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> ListWorkspacesResponse:
    """List all workspaces across all projects, ordered by recent activity."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace_dicts = transaction.get_all_workspaces()

    workspaces = [
        RecentWorkspaceResponse(
            object_id=row["object_id"],
            project_id=row["project_id"],
            description=row["description"],
            initialization_strategy=row["initialization_strategy"],
            source_branch=row["source_branch"],
            is_deleted=row["is_deleted"],
            created_at=row["created_at"],
            project_name=row["project_name"],
            agent_count=row["agent_count"],
            is_open=row["is_open"],
            last_activity_at=row["last_activity_at"],
            harness=row["harness"],
        )
        for row in workspace_dicts
    ]

    return ListWorkspacesResponse(workspaces=workspaces)


@router.patch("/api/v1/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    request: Request,
    update_request: UpdateWorkspaceRequest,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceResponse:
    """Update a workspace's description and/or target branch."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        try:
            updated_workspace = services.workspace_service.update_workspace(
                workspace_id=validated_workspace_id,
                description=update_request.description,
                target_branch=update_request.target_branch,
                is_open=update_request.is_open,
                transaction=transaction,
            )
        except WorkspaceNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found") from e
        logger.info("Updated workspace {}", workspace_id)

    # Refresh diffs after the transaction commits so the frontend picks up the
    # new target-branch diff via the diffUpdatedAt reactivity.
    if update_request.target_branch is not None:
        services.workspace_service.refresh_workspace_diff(validated_workspace_id, include_target_branch_diff=True)

    return _workspace_to_response(updated_workspace)


@router.post("/api/v1/workspaces/batch-update-open-state")
def batch_update_open_state(
    request: Request,
    batch_request: BatchUpdateOpenStateRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Set is_open on multiple workspaces in a single transaction."""
    logger.info("Batch updating is_open={} for {} workspaces", batch_request.is_open, len(batch_request.workspace_ids))
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        for ws_id_str in batch_request.workspace_ids:
            ws_id = validate_workspace_id(ws_id_str)
            try:
                services.workspace_service.update_workspace(
                    workspace_id=ws_id,
                    is_open=batch_request.is_open,
                    transaction=transaction,
                )
            except WorkspaceNotFoundError:
                pass  # Skip workspaces that no longer exist


@router.get("/api/v1/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceResponse:
    """Get a workspace by ID."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
        return _workspace_to_response(workspace)


@router.get("/api/v1/projects/{project_id}/workspaces")
def list_workspaces(
    project_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> list[WorkspaceResponse]:
    """List workspaces for a project."""
    validated_project_id = validate_project_id(project_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspaces = transaction.get_workspaces(project_id=validated_project_id)
        return [_workspace_to_response(w) for w in workspaces]


@router.delete("/api/v1/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Delete a workspace and all its agents (cascade delete)."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    # immediate=True: serialize the cascade-delete with concurrent workspace
    # writers (refresh_workspace_diff, update_workspace, etc.) so neither
    # side can stomp on the other (SCU-168).
    with user_session.open_transaction(services, immediate=True) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        # Cascade delete: clean up all agents in the workspace
        workspace_tasks = _get_tasks_for_workspace(workspace, transaction)
        for task in workspace_tasks:
            _cleanup_task_file_attachments(task.object_id, services, transaction)
            try:
                services.task_service.delete_task(task.object_id, transaction)
                logger.debug("Cascade-deleted agent {} from workspace {}", task.object_id, workspace_id)
            except TaskNotFound:
                logger.debug("Agent {} already deleted during cascade", task.object_id)

        services.workspace_service.delete_workspace(validated_workspace_id, transaction)
        logger.info("Deleted workspace {} with {} agents", workspace_id, len(workspace_tasks))


@router.get("/api/v1/workspaces/{workspace_id}/diff")
def get_workspace_diff(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
    force_refresh: bool = False,
    context_lines: int = 3,
    scope: str = "uncommitted",
) -> WorkspaceDiffResponse:
    """Get the latest diff for a workspace.

    The diff shows changes from workspace.source_git_hash to current state.
    Use force_refresh=true to regenerate the diff before returning.
    Use scope=vs-target-branch to include the target branch diff.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)
    include_target_branch_diff = scope == "vs-target-branch"

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        diff = services.workspace_service.get_workspace_diff(
            validated_workspace_id,
            transaction,
            force_refresh=force_refresh,
            context_lines=context_lines,
            include_target_branch_diff=include_target_branch_diff,
        )
        return WorkspaceDiffResponse(diff=diff)


@router.get("/api/v1/workspaces/{workspace_id}/commits")
def get_workspace_commits(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> CommitHistoryResponse:
    """Get the commit history for a workspace branch.

    Returns commits from HEAD back to the fork point where the current branch
    diverged from the target branch.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        try:
            commits, fork_point = services.workspace_service.get_commit_history(validated_workspace_id, transaction)
        except WorkspaceNotFoundError:
            return CommitHistoryResponse(commits=[], fork_point=None)

        return CommitHistoryResponse(
            commits=[
                CommitInfo(
                    hash=c["hash"],
                    short_hash=c["short_hash"],
                    message=c["message"],
                    author_name=c["author_name"],
                    timestamp=c["timestamp"],
                    parent_hashes=c.get("parent_hashes", []),
                    files=[
                        CommitFileInfo(
                            path=f["path"],
                            status=f["status"],
                            old_path=f["old_path"],
                            additions=f["additions"],
                            deletions=f["deletions"],
                        )
                        for f in c["files"]
                    ],
                )
                for c in commits
            ],
            fork_point=fork_point,
        )


@router.get("/api/v1/workspaces/{workspace_id}/commit-diff")
def get_workspace_commit_diff(
    workspace_id: str,
    request: Request,
    commit_hash: str,
    user_session: UserSession = Depends(get_user_session),
) -> CommitDiffResponse:
    """Get the unified diff for a single commit."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        try:
            diff_text, resolved_hash, parent_hash = services.workspace_service.get_commit_diff(
                validated_workspace_id, commit_hash, transaction
            )
        except WorkspaceNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found") from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        return CommitDiffResponse(
            diff=diff_text,
            commit_hash=resolved_hash,
            parent_hash=parent_hash,
        )


@router.post("/api/v1/workspaces/{workspace_id}/discard-file")
def discard_workspace_file(
    workspace_id: str,
    request: Request,
    discard_request: DiscardFileRequest,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceGitOperationResponse:
    """Discard changes to a single file in a workspace.

    Uses git checkout for tracked files and git clean for untracked files.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        result = services.workspace_service.discard_file(
            validated_workspace_id,
            discard_request.file_path,
            transaction,
        )
        logger.info(
            "Discarded file {} in workspace {}: success={}",
            discard_request.file_path,
            workspace_id,
            result.success,
        )
        return WorkspaceGitOperationResponse(result=result)


def _resolve_open_file_target(
    workspace: Workspace,
    services: CompleteServiceCollection,
    transaction: TaskAndDataModelTransaction,
    file_path: str,
) -> Path:
    """Resolve a CLI-provided absolute path to a host-readable file.

    Returns the resolved Path on success. Raises HTTPException(status_code=404,
    detail={"code": "file_not_found", "message": ...}) otherwise.

    Mirrors the dual-branch logic in workspace_read_file: prefer the workspace
    environment, fall back to the host filesystem for any absolute path the
    host process can read.
    """
    resolved = Path(file_path)
    if not resolved.is_absolute():
        raise HTTPException(
            status_code=400,
            detail={"code": "file_not_absolute", "message": f"path must be absolute: {file_path}"},
        )

    tasks = transaction.get_tasks_for_project(workspace.project_id)
    for task in tasks:
        if isinstance(task.current_state, AgentTaskStateV2) and task.current_state.workspace_id == workspace.object_id:
            environment = services.task_service.get_task_environment(task.object_id, transaction)
            if environment is not None and environment.exists(str(resolved)):
                return resolved

    if resolved.is_file():
        return resolved

    raise HTTPException(
        status_code=404,
        detail={"code": "file_not_found", "message": file_path},
    )


@router.post("/api/v1/workspaces/{workspace_id}/ui/open-file")
def workspace_ui_open_file(
    workspace_id: str,
    request: Request,
    open_file_request: OpenFileUiRequest,
    user_session: UserSession = Depends(get_user_session),
) -> Response:
    """Open a file as the active tab in the user's diff panel for this workspace.

    Emits an OpenFileUiAction event over the per-user WebSocket fan-out so
    connected frontends update their per-workspace diff-panel atoms.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(
                status_code=404,
                detail={"code": "workspace_not_found", "message": f"workspace {workspace_id} not found"},
            )
        if not workspace.is_open:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "workspace_not_open",
                    "message": f"workspace {workspace_id} is not open (is_open=False); cannot show files in a closed workspace",
                },
            )

        assert isinstance(transaction, TaskAndDataModelTransaction)
        resolved_path = _resolve_open_file_target(
            workspace=workspace,
            services=services,
            transaction=transaction,
            file_path=open_file_request.file_path,
        )

    publish_ui_action(
        OpenFileUiAction(
            workspace_id=workspace.object_id,
            file_path=str(resolved_path),
            mode=open_file_request.mode,
        )
    )

    return Response(status_code=204)


def _ensure_webview_target_workspace(
    workspace_id: str,
    request: Request,
    user_session: UserSession,
) -> WorkspaceID:
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(
                status_code=404,
                detail={"code": "workspace_not_found", "message": f"workspace {workspace_id} not found"},
            )
        if not workspace.is_open:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "workspace_not_open",
                    "message": f"workspace {workspace_id} is not open (is_open=False); cannot drive the webview in a closed workspace",
                },
            )
        return workspace.object_id


@router.post("/api/v1/workspaces/{workspace_id}/ui/webview/navigate")
def workspace_ui_webview_navigate(
    workspace_id: str,
    request: Request,
    navigate_request: WebviewNavigateRequest,
    user_session: UserSession = Depends(get_user_session),
) -> Response:
    """Drive the in-app Browser panel for this workspace to navigate to a URL.

    Emits a WebviewCommandUiAction event over the per-user WebSocket fan-out so
    connected frontends update their per-workspace browser-panel atoms.
    """
    target_workspace_id = _ensure_webview_target_workspace(workspace_id, request, user_session)
    publish_ui_action(
        WebviewCommandUiAction(
            workspace_id=target_workspace_id,
            seq=next_webview_seq(target_workspace_id),
            kind="navigate",
            url=navigate_request.url,
        )
    )
    return Response(status_code=204)


@router.post("/api/v1/workspaces/{workspace_id}/ui/webview/refresh")
def workspace_ui_webview_refresh(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> Response:
    """Drive the in-app Browser panel for this workspace to reload the current URL."""
    target_workspace_id = _ensure_webview_target_workspace(workspace_id, request, user_session)
    publish_ui_action(
        WebviewCommandUiAction(
            workspace_id=target_workspace_id,
            seq=next_webview_seq(target_workspace_id),
            kind="refresh",
            url=None,
        )
    )
    return Response(status_code=204)


@router.post("/api/v1/workspaces/{workspace_id}/read-file")
def workspace_read_file(
    workspace_id: str,
    request: Request,
    read_file_request: ReadFileRequest,
    user_session: UserSession = Depends(get_user_session),
) -> ReadFileAtRefResponse:
    """Read a file from the workspace's working directory."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        # Find any task in this workspace to get the environment
        tasks = transaction.get_tasks_for_project(workspace.project_id)  # pyre-fixme[16]
        workspace_task = None
        for task in tasks:
            if (
                isinstance(task.current_state, AgentTaskStateV2)
                and task.current_state.workspace_id == validated_workspace_id
            ):
                workspace_task = task
                break

        if workspace_task is None:
            raise HTTPException(status_code=400, detail="No agent found in workspace to read files from")

        environment = services.task_service.get_task_environment(workspace_task.object_id, transaction)
        if environment is None:
            raise HTTPException(status_code=400, detail="Workspace environment not found")

        task_repo_path = environment.get_working_directory()
        file_path = task_repo_path / read_file_request.file_path

        # Try the workspace environment first (handles workspace-relative files).
        # Fall back to reading directly from the host filesystem for any
        # absolute path the host process can read. The backend runs as the
        # authenticated user, so "host-readable" == "user-readable" — no
        # privilege boundary is crossed by widening this gate.
        use_direct_read = False
        if not environment.exists(str(file_path)):
            if file_path.is_absolute() and file_path.is_file():
                use_direct_read = True
            else:
                raise HTTPException(status_code=404, detail="File not found")

        try:
            content: str | bytes = file_path.read_text() if use_direct_read else environment.read_file(str(file_path))
        except UnicodeDecodeError:
            # Text read failed — binary file. Read in binary mode and base64-encode.
            logger.debug("Text read failed for {}, falling back to binary mode", file_path)
            try:
                if use_direct_read:
                    raw_bytes = file_path.read_bytes()
                else:
                    raw = environment.read_file(str(file_path), mode="rb")
                    assert isinstance(raw, bytes)
                    raw_bytes = raw
                encoded = base64.b64encode(raw_bytes).decode("ascii")
                return ReadFileAtRefResponse(content=encoded, encoding="base64")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to read file {file_path}") from e

        if isinstance(content, bytes):
            encoded = base64.b64encode(content).decode("ascii")
            return ReadFileAtRefResponse(content=encoded, encoding="base64")

        return ReadFileAtRefResponse(content=content, encoding="utf-8")


_WORKSPACE_FILES_RETRY_AFTER_SECONDS = "1"


@router.get("/api/v1/workspaces/{workspace_id}/files")
def get_workspace_files(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceFileListResponse:
    """List all files and directories in a workspace's working directory."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        try:
            file_paths = services.workspace_service.get_workspace_files(validated_workspace_id, transaction)
        except WorkspaceNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found") from e
        except WorkspaceFilesUnavailableError as e:
            # Distinguish a transient git failure (e.g. lock contention) from a
            # legitimately empty workspace. Retry-After tells callers it's safe
            # to come back shortly; clients should treat this as retryable.
            raise HTTPException(
                status_code=503,
                detail=f"Workspace file list temporarily unavailable: {e}",
                headers={"Retry-After": _WORKSPACE_FILES_RETRY_AFTER_SECONDS},
            ) from e

    directories: set[str] = set()
    for file_path in file_paths:
        parts = file_path.split("/")
        for i in range(1, len(parts)):
            directories.add("/".join(parts[:i]))

    entries: list[WorkspaceFileEntry] = []
    for dir_path in sorted(directories):
        entries.append(WorkspaceFileEntry(path=dir_path, type="directory"))
    for fp in file_paths:
        entries.append(WorkspaceFileEntry(path=fp, type="file"))

    return WorkspaceFileListResponse(files=entries)


@router.post("/api/v1/workspaces/{workspace_id}/open-in-os")
def workspace_open_in_os(
    workspace_id: str,
    request: Request,
    open_request: OpenInOsRequest,
    user_session: UserSession = Depends(get_user_session),
) -> Response:
    """Open a file or its containing folder in the OS default application."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        working_dir = services.workspace_service.get_workspace_working_directory(workspace, transaction)
        if working_dir is None:
            raise HTTPException(status_code=400, detail="Workspace environment not initialized")

    abs_path = (working_dir / open_request.path).resolve()
    if not abs_path.is_relative_to(working_dir.resolve()):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if sys.platform == "darwin":
        if open_request.action == "open_file":
            subprocess.Popen(["open", str(abs_path)])
        else:
            subprocess.Popen(["open", "-R", str(abs_path)])
    elif sys.platform.startswith("linux"):
        if open_request.action == "open_file":
            subprocess.Popen(["xdg-open", str(abs_path)])
        else:
            subprocess.Popen(["xdg-open", str(abs_path.parent)])
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {sys.platform}")

    return Response(status_code=200)


@router.post("/api/v1/workspaces/{workspace_id}/read-file-at-ref")
def workspace_read_file_at_ref(
    workspace_id: str,
    request: Request,
    read_at_ref_request: ReadFileAtRefRequest,
    user_session: UserSession = Depends(get_user_session),
) -> ReadFileAtRefResponse:
    """Read a file's content at a specific git ref."""
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
        if workspace is None or workspace.is_deleted:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

        try:
            result = services.workspace_service.read_file_at_ref(
                validated_workspace_id,
                read_at_ref_request.path,
                read_at_ref_request.git_ref,
                transaction,
            )
        except FileNotFoundAtRefError as e:
            raise HTTPException(status_code=404, detail=f"File not found at ref: {e}") from e

    return ReadFileAtRefResponse(content=result.content, encoding=result.encoding)


@router.get("/api/v1/skills")
def get_skills(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
    project_id: str | None = None,
    workspace_id: str | None = None,
) -> list[SkillInfo]:
    """Get available Claude Code skills.

    Exactly one of project_id or workspace_id must be provided.

    When workspace_id is given, discovers skills from the workspace's working
    directory (which may be a clone in CLONE mode). Falls back to the project's
    local repo if the workspace environment hasn't been initialized yet.

    When project_id is given, discovers skills from the project's local
    repository. Used on the Add Workspace page where no workspace exists yet.
    """
    if workspace_id is not None and project_id is not None:
        raise HTTPException(status_code=400, detail="Provide either project_id or workspace_id, not both")
    if workspace_id is None and project_id is None:
        raise HTTPException(status_code=400, detail="Either project_id or workspace_id is required")

    services = get_services_from_request_or_websocket(request)
    plugin_dirs = get_plugin_dirs()

    if workspace_id is not None:
        validated_workspace_id = validate_workspace_id(workspace_id)
        with user_session.open_transaction(services) as transaction:
            workspace = transaction.get_workspace(validated_workspace_id)
            if workspace is None or workspace.is_deleted:
                raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

            working_dir = services.workspace_service.get_workspace_working_directory(workspace, transaction)

            if working_dir is None:
                # Environment not yet initialized — fall back to the project's local repo.
                project = transaction.get_project(workspace.project_id)
                if project is None:
                    raise HTTPException(status_code=404, detail="Workspace project not found")
                try:
                    with services.git_repo_service.open_local_user_git_repo_for_read(project) as repo:
                        return discover_skills(repo.get_repo_path(), plugin_dirs=plugin_dirs)
                except Exception as e:
                    log_exception(e, "Failed to get skills")
                    raise HTTPException(status_code=500, detail="Failed to get skills") from e

        try:
            return discover_skills(working_dir, plugin_dirs=plugin_dirs)
        except Exception as e:
            log_exception(e, "Failed to get skills")
            raise HTTPException(status_code=500, detail="Failed to get skills") from e

    else:
        assert project_id is not None
        validated_project_id = validate_project_id(project_id)
        with user_session.open_transaction(services) as transaction:
            project = transaction.get_project(validated_project_id)
            if project is None:
                raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
            try:
                with services.git_repo_service.open_local_user_git_repo_for_read(project) as repo:
                    return discover_skills(repo.get_repo_path(), plugin_dirs=plugin_dirs)
            except Exception as e:
                log_exception(e, "Failed to get skills")
                raise HTTPException(status_code=500, detail="Failed to get skills") from e


# =====================
# Workspace-Scoped Agent Endpoints
# =====================


def _get_workspace_or_404(
    workspace_id: str,
    transaction: DataModelTransaction,
) -> Workspace:
    """Validate workspace_id and return the workspace, raising 404 if not found."""
    validated_id = validate_workspace_id(workspace_id)
    workspace = transaction.get_workspace(validated_id)
    if workspace is None or workspace.is_deleted:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
    return workspace


# DELIBERATE-TEMPORARY: workspace-bound harness selection.
def _agent_config_for_workspace(workspace: Workspace) -> ClaudeCodeSDKAgentConfig | PiAgentConfig:
    if workspace.harness == HarnessName.PI:
        return PiAgentConfig()
    return ClaudeCodeSDKAgentConfig()


def _get_tasks_for_workspace(
    workspace: Workspace,
    transaction: DataModelTransaction,
) -> list[Task]:
    """Get all tasks belonging to a workspace."""
    all_tasks = transaction.get_tasks_for_project(workspace.project_id)  # pyre-fixme[16]
    return [
        t
        for t in all_tasks
        if isinstance(t.current_state, AgentTaskStateV2)
        and t.current_state.workspace_id == workspace.object_id
        and not t.is_deleting
        and not t.is_deleted
    ]


def _validate_agent_in_workspace(
    agent_id: str,
    workspace: Workspace,
    transaction: DataModelTransaction,
    services: CompleteServiceCollection,
) -> Task:
    """Validate that agent_id belongs to the workspace and return the task."""
    validated_task_id = validate_task_id(agent_id)
    task = services.task_service.get_task(validated_task_id, transaction)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if not isinstance(task.current_state, AgentTaskStateV2):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if task.current_state.workspace_id != workspace.object_id:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found in workspace {workspace.object_id}")
    return task


def _compute_next_agent_name(existing_tasks: list[Task]) -> str:
    """Compute the next auto-generated agent name like 'Agent N'.

    Reuses the lowest available number so that deleting "Agent 1" and creating
    a new agent produces "Agent 1" again instead of an ever-increasing counter.
    """
    pattern = re.compile(r"^Agent (\d+)$")
    used_numbers: set[int] = set()
    for task in existing_tasks:
        if isinstance(task.current_state, AgentTaskStateV2) and task.current_state.title:
            match = pattern.match(task.current_state.title)
            if match:
                used_numbers.add(int(match.group(1)))
    n = 1
    while n in used_numbers:
        n += 1
    return f"Agent {n}"


@router.post("/api/v1/workspaces/{workspace_id}/agents")
def create_workspace_agent(
    workspace_id: str,
    request: Request,
    agent_request: CreateAgentRequest,
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> CodingAgentTaskView:
    """Create a new agent in a workspace.

    If prompt is provided, creates and starts the agent (same as start_task).
    If prompt is None/empty, creates the agent in a waiting state with auto-generated name.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        project = transaction.get_project(workspace.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Workspace project not found")

        if agent_request.prompt:
            # Delegate to existing start_task logic
            model = agent_request.model
            if model is None:
                raise HTTPException(
                    status_code=422,
                    detail=[
                        {
                            "loc": ["body", "model"],
                            "msg": "Model is required when providing a prompt",
                            "type": "value_error.missing",
                        }
                    ],
                )

            task_request = StartTaskRequest(
                prompt=agent_request.prompt,
                interface=agent_request.interface,
                model=model,
                files=agent_request.files,
                name=agent_request.name,
                workspace_id=validated_workspace_id,
                enter_plan_mode=agent_request.enter_plan_mode,
                fast_mode=agent_request.fast_mode,
                effort=agent_request.effort,
                sent_via=agent_request.sent_via,
            )
            return start_task(
                project_id=workspace.project_id,
                request=request,
                task_request=task_request,
                user_session=user_session,
                settings=settings,
            )

        # No prompt — create agent in waiting state
        _prevent_action_if_out_of_free_space(services)

        workspace_tasks = _get_tasks_for_workspace(workspace, transaction)
        task_name = agent_request.name or _compute_next_agent_name(workspace_tasks)
        task_id = TaskID()

        # Check if this is the user's very first agent ever (including deleted ones).
        # get_all_tasks() includes deleted tasks, so this stays False once any agent
        # has ever been created — even if all workspaces were later deleted.
        # Skip during integration tests to avoid injecting unexpected messages.
        is_first_agent = (
            not settings.TESTING.INTEGRATION_ENABLED
            and len(workspace_tasks) == 0
            and len(transaction.get_all_tasks()) == 0  # pyre-fixme[16]
        )

        agent_config = _agent_config_for_workspace(workspace)

        with services.git_repo_service.open_local_user_git_repo_for_read(project) as repo:
            initial_commit_hash = repo.get_current_commit_hash()

        initial_task_state = AgentTaskStateV2(
            title=task_name,
            workspace_id=validated_workspace_id,
        )

        task = Task(
            object_id=task_id,
            max_seconds=None,
            organization_reference=user_session.organization_reference,
            user_reference=user_session.user_reference,
            project_id=project.object_id,
            input_data=AgentTaskInputsV2(
                agent_config=agent_config,
                git_hash=initial_commit_hash,
                system_prompt=project.default_system_prompt,
                default_model=agent_request.model,
            ),
            current_state=initial_task_state,
        )

    root_concurrency_group = get_root_concurrency_group(request)
    intro_message = None
    with (
        root_concurrency_group.make_concurrency_group(name="create_agent") as _concurrency_group,
        user_session.open_transaction(services) as transaction,
    ):
        inserted_task = services.task_service.create_task(task, transaction)

        # Auto-send intro help message for first-time users
        if is_first_agent:
            intro_message = ChatInputUserMessage(
                text="/sculptor:help I just set up Sculptor for the first time. What should I know to get started?",
                message_id=AgentMessageID(),
                model_name=agent_request.model or LLMModel.CLAUDE_4_OPUS,
            )
            services.task_service.create_message(
                message=intro_message,
                task_id=inserted_task.object_id,
                transaction=transaction,
            )

    task_view = create_initial_task_view(inserted_task, settings)
    assert isinstance(task_view, CodingAgentTaskView)
    if intro_message is not None:
        task_view.add_message(intro_message)
    return task_view


class ResolveAgentResponse(SerializableModel):
    agent_id: str


@router.get("/api/v1/agents/by-prefix/{prefix}")
def resolve_agent_by_prefix(
    prefix: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> ResolveAgentResponse:
    """Resolve a TaskID prefix to a unique full agent id for the authenticated user."""
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        tasks = transaction.get_tasks_for_user(user_session.user_reference)  # pyre-fixme[16]
    matches = [
        t.object_id
        for t in tasks
        if isinstance(t.input_data, AgentTaskInputsV2) and not t.is_deleted and str(t.object_id).startswith(prefix)
    ]
    if len(matches) == 0:
        raise HTTPException(status_code=404, detail=f"no agent matches prefix '{prefix}'")
    if len(matches) > 1:
        match_list = ", ".join(str(m) for m in matches)
        raise HTTPException(
            status_code=409,
            detail=f"ambiguous prefix '{prefix}' matches {len(matches)} agents: {match_list}",
        )
    return ResolveAgentResponse(agent_id=str(matches[0]))


class CIBabysitterWorkspaceStateResponse(SerializableModel):
    """Per-workspace CI Babysitter state, surfaced to the PR popover."""

    workspace_id: WorkspaceID
    paused: bool
    retry_count: int
    retry_cap: int
    retired: bool
    at_cap: bool


class CIBabysitterPauseRequest(SerializableModel):
    paused: bool


def _build_ci_babysitter_state_response(
    workspace_id: WorkspaceID, services: CompleteServiceCollection
) -> CIBabysitterWorkspaceStateResponse:
    config = get_user_config_instance()
    snapshot = services.ci_babysitter_service.get_state_snapshot(workspace_id)
    if snapshot is None:
        return CIBabysitterWorkspaceStateResponse(
            workspace_id=workspace_id,
            paused=False,
            retry_count=0,
            retry_cap=config.ci_babysitter.retry_cap,
            retired=False,
            at_cap=False,
        )
    return CIBabysitterWorkspaceStateResponse(
        workspace_id=workspace_id,
        paused=snapshot.paused,
        retry_count=snapshot.retry_count,
        retry_cap=config.ci_babysitter.retry_cap,
        retired=snapshot.retired,
        at_cap=snapshot.at_cap,
    )


@router.get("/api/v1/workspaces/{workspace_id}/ci_babysitter")
def get_ci_babysitter_state(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> CIBabysitterWorkspaceStateResponse:
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        _get_workspace_or_404(workspace_id, transaction)
    return _build_ci_babysitter_state_response(validated_workspace_id, services)


@router.post("/api/v1/workspaces/{workspace_id}/ci_babysitter/pause")
def set_ci_babysitter_paused(
    workspace_id: str,
    request: Request,
    body: CIBabysitterPauseRequest,
    user_session: UserSession = Depends(get_user_session),
) -> CIBabysitterWorkspaceStateResponse:
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        _get_workspace_or_404(workspace_id, transaction)
    services.ci_babysitter_service.set_paused(validated_workspace_id, body.paused)
    return _build_ci_babysitter_state_response(validated_workspace_id, services)


@router.get("/api/v1/workspaces/{workspace_id}/agents")
def list_workspace_agents(
    workspace_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> tuple[TaskViewTypes, ...]:
    """List all agents in a workspace."""
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        tasks = _get_tasks_for_workspace(workspace, transaction)

    task_views: list[TaskViewTypes] = []
    for task in tasks:
        if not isinstance(task.input_data, AgentTaskInputsV2):
            continue
        task_view = create_initial_task_view(task, services.settings)
        task_view.update_task(task)
        task_views.append(task_view)

    return tuple(task_views)


@router.delete("/api/v1/workspaces/{workspace_id}/agents/{agent_id}")
def delete_workspace_agent(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Delete an agent from a workspace."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        _cleanup_task_file_attachments(task.object_id, services, transaction)

        try:
            services.task_service.delete_task(task.object_id, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Agent not found") from e


@router.patch("/api/v1/workspaces/{workspace_id}/agents/{agent_id}")
def rename_workspace_agent(
    workspace_id: str,
    agent_id: str,
    request: Request,
    rename_request: RenameAgentRequest,
    user_session: UserSession = Depends(get_user_session),
) -> CodingAgentTaskView:
    """Rename an agent."""
    services = get_services_from_request_or_websocket(request)
    settings = services.settings

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        assert isinstance(task.current_state, AgentTaskStateV2)
        updated_state = task.current_state.evolve(task.current_state.ref().title, rename_request.title)
        updated_task = task.evolve(task.ref().current_state, updated_state)
        transaction.upsert_task(updated_task)  # pyre-fixme[16]

        task_view = create_initial_task_view(updated_task, settings)
        assert isinstance(task_view, CodingAgentTaskView)
        task_view.update_task(updated_task)
        return task_view


@router.patch("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/mark-read")
def mark_workspace_agent_read(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> bool:
    """Mark an agent as read."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        try:
            services.task_service.mark_read(task.object_id, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Agent not found") from e

    return True


@router.patch("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/mark-unread")
def mark_workspace_agent_unread(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> bool:
    """Mark an agent as unread."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        try:
            services.task_service.mark_unread(task.object_id, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Agent not found") from e

    return True


@router.post("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/restore")
def restore_workspace_agent(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Restore a failed agent."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        try:
            services.task_service.restore_task(task.object_id, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Agent not found") from e
        except InvalidTaskOperation as e:
            raise HTTPException(status_code=400, detail="Agent is not in a failed state - cannot restore") from e


@router.get("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/diagnostics")
def get_workspace_agent_diagnostics(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> AgentDiagnosticsResponse:
    """Get diagnostics info for an agent (session ID and transcript file path)."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)
        working_dir = services.workspace_service.get_workspace_working_directory(workspace, transaction)

    if working_dir is None or workspace.environment_id is None:
        return AgentDiagnosticsResponse()

    # Read session_id from the per-task state directory on disk.
    # The environment_id stores the environment's root path (where state files live).
    # State files are under {environment_root}/state/tasks/{task_id}/
    environment_root = Path(workspace.environment_id)
    state_file = environment_root / STATE_DIRECTORY / TASKS_SUBDIRECTORY / str(task.object_id) / "session_id"

    session_id: str | None = None
    transcript_file_path: str | None = None

    try:
        session_id = state_file.read_text().strip()
    except (FileNotFoundError, OSError):
        pass

    if session_id and isinstance(task.input_data, AgentTaskInputsV2):
        # We don't hold an AgentExecutionEnvironment here (only the host-side
        # working directory), so call the harness's path-from-primitives
        # helper instead of the env-bound method.
        harness = get_harness_for_config(task.input_data.agent_config)
        jsonl_dir = harness.get_jsonl_path_for_working_directory(Path.home(), working_dir.resolve())
        if jsonl_dir is not None:
            transcript_file_path = str(jsonl_dir / f"{session_id}.jsonl")

    sculptor_transcript = (
        environment_root / ARTIFACTS_DIRECTORY / TASKS_SUBDIRECTORY / str(task.object_id) / "transcript.jsonl"
    )
    sculptor_transcript_file_path = str(sculptor_transcript) if sculptor_transcript.exists() else None

    return AgentDiagnosticsResponse(
        session_id=session_id,
        transcript_file_path=transcript_file_path,
        sculptor_transcript_file_path=sculptor_transcript_file_path,
    )


@router.post("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/messages")
def send_workspace_agent_messages(
    workspace_id: str,
    agent_id: str,
    request: Request,
    message_request: SendMessageRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Send a message to an agent via API interface."""
    services = get_services_from_request_or_websocket(request)
    _prevent_action_if_out_of_free_space(services)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        message_str = message_request.message
        if not message_str:
            raise HTTPException(
                status_code=422,
                detail=[{"loc": ["body", "message"], "msg": "Message required", "type": "value_error.missing"}],
            )

        saved_messages = services.task_service.get_saved_messages_for_task(task.object_id, transaction)
        assert isinstance(task.input_data, AgentTaskInputsV2), (
            f"Expected AgentTaskInputsV2 for agent message endpoint, got {type(task.input_data).__name__}"
        )
        harness = get_harness_for_config(task.input_data.agent_config)
        if message_request.enter_plan_mode and not harness.capabilities().supports_interactive_backchannel:
            raise HTTPException(
                status_code=400,
                detail="plan mode requires a harness that supports the interactive backchannel",
            )
        task_state = convert_agent_messages_to_task_update(
            saved_messages, task_id=task.object_id, completed_message_by_id={}, harness=harness
        )
        if task_state.pending_user_question is not None:
            raise HTTPException(
                status_code=409,
                detail="Cannot send a message while the agent is waiting for a response to AskUserQuestion.",
            )

        message_id = AgentMessageID()
        logger.info("Sending message {} to agent {}: {}", message_id, agent_id, message_str[:100])

        message = ChatInputUserMessage(
            message_id=message_id,
            text=message_str,
            model_name=message_request.model,
            files=message_request.files,
            enter_plan_mode=message_request.enter_plan_mode,
            exit_plan_mode=message_request.exit_plan_mode,
            fast_mode=message_request.fast_mode,
            effort=message_request.effort,
            sent_via=message_request.sent_via,
        )

        services.task_service.create_message(
            message=message,
            task_id=task.object_id,
            transaction=transaction,
        )


@router.post("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/answer_question")
def answer_workspace_agent_question(
    workspace_id: str,
    agent_id: str,
    request: Request,
    answer_request: AnswerQuestionRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Submit answers to an AskUserQuestion tool invocation."""
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

        # Persist the answer message. Since UserQuestionAnswerMessage is a PersistentUserMessage,
        # the agent runner picks it up and sends it to the agent to resume processing.
        answer_message = UserQuestionAnswerMessage(
            message_id=AgentMessageID(),
            answers=answer_request.answers,
            notes=answer_request.notes,
            question_data=answer_request.question_data,
            tool_use_id=answer_request.tool_use_id,
        )
        services.task_service.create_message(
            message=answer_message,
            task_id=task.object_id,
            transaction=transaction,
        )


@router.post("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/clear_context")
def clear_workspace_agent_context(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Clear agent context."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

    message_id = AgentMessageID()
    with await_message_response(message_id, task.object_id, services):
        with user_session.open_transaction(services) as transaction:
            services.task_service.create_message(
                message=ClearContextUserMessage(message_id=message_id),
                task_id=task.object_id,
                transaction=transaction,
            )


@router.post("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/interrupt")
def interrupt_workspace_agent(
    workspace_id: str,
    agent_id: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Interrupt a running agent."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

    message_id = AgentMessageID()
    with await_message_response(message_id, task.object_id, services):
        with user_session.open_transaction(services) as transaction:
            services.task_service.create_message(
                message=InterruptProcessUserMessage(message_id=message_id),
                task_id=task.object_id,
                transaction=transaction,
            )


@router.post("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/btw")
def btw_agent(
    workspace_id: str,
    agent_id: str,
    request: Request,
    btw_request: BtwRequest,
    user_session: UserSession = Depends(get_user_session),
) -> Response:
    """Run a single forked `/btw` Haiku turn that streams back via the unified WS."""
    if not btw_request.question.strip():
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "question"], "msg": "Question required", "type": "value_error.missing"}],
        )
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)
        environment = services.task_service.get_task_environment(task.object_id, transaction)
        saved_messages = services.task_service.get_saved_messages_for_task(task.object_id, transaction)

    if environment is None:
        raise HTTPException(status_code=409, detail={"reason": "no_session_yet"})

    agent_environment = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    # Main-agent fake-claude detection: if the most recent user-authored chat
    # message picked a fake-claude model, fork using FakeClaude instead of the
    # real binary so integration tests exercise the /btw path end-to-end.
    latest_model: LLMModel | None = None
    main_agent_started = False
    for saved in reversed(saved_messages):
        if isinstance(saved, ChatInputUserMessage):
            main_agent_started = True
            latest_model = saved.model_name
            break
    if latest_model is None and isinstance(task.input_data, AgentTaskInputsV2):
        latest_model = task.input_data.default_model
    is_fake_claude = latest_model in (LLMModel.FAKE_CLAUDE, LLMModel.FAKE_CLAUDE_2)

    try:
        services.btw_service.run_btw_for_task(
            environment=agent_environment,
            task_id=task.object_id,
            workspace_id=WorkspaceID(workspace_id),
            question=btw_request.question,
            request_id=btw_request.request_id,
            is_fake_claude=is_fake_claude,
            main_agent_started=main_agent_started,
        )
    except NoBtwSessionAvailable as exc:
        raise HTTPException(status_code=409, detail={"reason": "no_session_yet"}) from exc

    return Response(status_code=202)


@router.get("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/artifacts/{artifact_name}")
def get_workspace_agent_artifact(
    workspace_id: str,
    agent_id: str,
    artifact_name: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> ArtifactDataResponse:
    """Get an artifact for an agent."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        _validate_agent_in_workspace(agent_id, workspace, transaction, services)

    return _get_typed_artifact_data(artifact_name, services, agent_id, user_session)


@router.delete("/api/v1/workspaces/{workspace_id}/agents/{agent_id}/messages/{message_id}")
def delete_workspace_agent_message(
    workspace_id: str,
    agent_id: str,
    message_id: AgentMessageID,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Delete a message from an agent."""
    services = get_services_from_request_or_websocket(request)

    with user_session.open_transaction(services) as transaction:
        workspace = _get_workspace_or_404(workspace_id, transaction)
        task = _validate_agent_in_workspace(agent_id, workspace, transaction, services)

    new_message_id = AgentMessageID()
    with await_message_response(new_message_id, task.object_id, services):
        with user_session.open_transaction(services) as transaction:
            services.task_service.create_message(
                message=RemoveQueuedMessageUserMessage(message_id=new_message_id, target_message_id=message_id),
                task_id=task.object_id,
                transaction=transaction,
            )


@contextlib.contextmanager
def await_message_response(
    message_id: AgentMessageID,
    task_id: TaskID,
    services: CompleteServiceCollection,
) -> Iterator[None]:
    with services.task_service.subscribe_to_task(task_id) as updates_queue:
        yield
        logger.debug("Waiting for response to message {} in task {}", message_id, task_id)
        while True:
            try:
                update = updates_queue.get(timeout=1.0)
            except queue.Empty:
                pass
            else:
                if isinstance(update, PersistentRequestCompleteAgentMessage):
                    if update.request_id == message_id:
                        break


def _prevent_action_if_out_of_free_space(services: CompleteServiceCollection) -> None:
    user_config = get_user_config_instance()
    free_gb = (_get_disk_bytes_free(services.settings) or 1_000_000_000_000) / (1024 * 1024 * 1024)
    if user_config is not None and free_gb < user_config.min_free_disk_gb:
        logger.warning("Cannot start a task if you have insufficient free space")
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient disk space ({user_config.min_free_disk_gb} GB free space required to prevent filling your disk)\nPlease either free some space (eg, by deleting old tasks) or increase min_free_disk_gb in settings.",
        )


@router.get("/api/v1/telemetry_info")
def get_telemetry_info(user_session: UserSession = Depends(get_user_session)) -> telemetry.TelemetryInfo:
    """Returns telemetry info for the current user.

    If the current user has not initialized their configuration, use an
    anonymous config.
    """
    return get_logged_in_or_anonymous_telemetry_info()


def get_logged_in_or_anonymous_telemetry_info() -> telemetry.TelemetryInfo:
    """Returns telemetry info for the current user.

    If the current user has not initialized their configuration, use an
    anonymous config.
    """
    logged_in_info = get_telemetry_info_impl()
    if not logged_in_info:
        return get_onboarding_telemetry_info()
    return logged_in_info


# ====================
# Onboarding routes and Helpers
# ====================


@router.get("/api/v1/config/status")
def get_config_status(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> ConfigStatusResponse:
    """Check if user config exists and what fields are configured"""
    user_config = get_user_config_instance()

    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        projects = transaction.get_projects(organization_reference=user_session.organization_reference)
    has_project = len(projects) > 0

    if not user_config:
        return ConfigStatusResponse(
            has_email=False,
            has_privacy_consent=False,
            has_project=has_project,
            has_dependencies_passing=False,
        )

    services = get_services_from_request_or_websocket(request)
    dep_status = services.dependency_management_service.get_status()
    deps_passing = (
        dep_status.git.installed and dep_status.claude.installed and dep_status.claude.is_version_in_range is not False
    )
    return ConfigStatusResponse(
        has_email=bool(user_config.user_email) and check_is_user_email_field_valid(user_config),
        has_privacy_consent=user_config.is_privacy_policy_consented,
        has_project=has_project,
        has_dependencies_passing=bool(deps_passing),
    )


@router.post("/api/v1/config/email")
def save_user_email(
    request: Request,
    email_config_request: EmailConfigRequest,
    user_session: UserSession = Depends(get_user_session),
) -> telemetry.TelemetryInfo:
    """Save user email during onboarding

    This function will determine the updated TelemetryInfo for the signed in user, and return that to the frontend.
    """
    # Get or create user config (since this is the first step)
    user_config = get_user_config_instance()

    user_config = model_update(
        user_config,
        {
            "user_email": email_config_request.user_email,
            "user_id": create_user_id(str(email_config_request.user_email)),
            "user_full_name": email_config_request.full_name,
            "organization_id": create_organization_id(str(email_config_request.user_email)),
            # Saving user email counts as consenting to the Policy email
            "is_privacy_policy_consented": True,
            # Telemetry choice comes from the welcome-step checkbox
            "is_telemetry_level_set": True,
            **get_privacy_settings_for_telemetry(email_config_request.is_telemetry_enabled).model_dump(),
        },
    )

    # The server log is bundled into bug-report diagnostics uploads, so never
    # write the actual email/name into it.
    logger.info(
        "Saved user profile (has_full_name={}, did_opt_in_to_marketing={})",
        email_config_request.full_name is not None,
        email_config_request.did_opt_in_to_marketing,
    )
    save_config(user_config, get_config_path())
    set_user_config_instance(user_config)

    return get_logged_in_or_anonymous_telemetry_info()


@router.post("/api/v1/config/skip_account")
def skip_account_setup(
    request: Request,
    skip_account_request: SkipAccountSetupRequest,
    user_session: UserSession = Depends(get_user_session),
) -> telemetry.TelemetryInfo:
    """Complete the onboarding welcome step without an account.

    The user keeps the anonymous, instance-id-based identity (no email or
    name); only their telemetry choice and the privacy-policy consent are
    recorded. Telemetry events therefore stay anonymous.
    """
    user_config = get_user_config_instance()

    user_config = model_update(
        user_config,
        {
            # Continuing past the welcome step counts as consenting to the policy
            "is_privacy_policy_consented": True,
            "is_telemetry_level_set": True,
            **get_privacy_settings_for_telemetry(skip_account_request.is_telemetry_enabled).model_dump(),
        },
    )

    save_config(user_config, get_config_path())
    set_user_config_instance(user_config)

    return get_logged_in_or_anonymous_telemetry_info()


@router.get("/api/v1/config/dependencies")
def get_dependencies_status(
    request: Request, user_session: UserSession = Depends(get_user_session)
) -> DependenciesStatus:
    """Check if required dependencies are installed."""
    services = get_services_from_request_or_websocket(request)
    service = services.dependency_management_service
    ds = service.get_status()

    return ds


@router.post("/api/v1/dependencies/install")
def install_dependency(
    request: Request,
    tool: str = "CLAUDE",
    user_session: UserSession = Depends(get_user_session),
) -> InstallResult:
    """Trigger installation of a managed dependency binary."""
    try:
        dependency = Dependency(tool)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}")

    services = get_services_from_request_or_websocket(request)
    return services.dependency_management_service.install_managed(dependency)


@router.post("/api/v1/dependencies/auth")
def authenticate_dependency(
    request: Request,
    tool: str = "CLAUDE",
    user_session: UserSession = Depends(get_user_session),
) -> AuthResult:
    """Trigger dependency authentication via browser login."""
    try:
        dependency = Dependency(tool)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}")

    services = get_services_from_request_or_websocket(request)
    return services.dependency_management_service.run_auth_login(dependency)


@router.post("/api/v1/config/complete")
def complete_onboarding(request: Request, user_session: UserSession = Depends(get_user_session)) -> None:
    """Complete onboarding by saving config to disk and initializing services"""
    user_config = get_user_config_instance()
    if not user_config:
        raise HTTPException(status_code=400, detail="User config not initialized")
    # An empty email means the user skipped account setup on the welcome step
    # (anonymous identity); only non-empty emails are validated.
    if user_config.user_email and not check_is_user_email_field_valid(user_config):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if not user_config.user_email and not user_config.is_privacy_policy_consented:
        raise HTTPException(status_code=400, detail="Welcome step has not been completed")

    # Ensure privacy consent and telemetry level are set for returning users
    # who may have created their account before these fields were added.
    updates: dict = {}
    if not user_config.is_privacy_policy_consented:
        updates["is_privacy_policy_consented"] = True
    if not user_config.is_telemetry_level_set:
        updates["is_telemetry_level_set"] = True
        updates.update(get_privacy_settings_for_telemetry(True).model_dump())
    if updates:
        user_config = model_update(user_config, updates)
        save_config(user_config, get_config_path())
        set_user_config_instance(user_config)

    logger.info("Onboarding completed successfully")


@router.get("/api/v1/config")
def get_user_config(request: Request, user_session: UserSession = Depends(get_user_session)) -> UserConfig | None:
    """Get the current user config"""
    return get_user_config_instance()


# The SDK-facing flags that POST /api/v1/config/telemetry owns. PUT
# /api/v1/config rejects requests that would change any of them.
_TELEMETRY_FLAGS = (
    "is_error_reporting_enabled",
    "is_product_analytics_enabled",
    "is_session_recording_enabled",
)


@router.put("/api/v1/config")
def update_user_config(
    update_config_request: UpdateUserConfigRequest,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> UserConfig:
    """Update user config — merges the provided fields into the current config.

    ``user_config`` is a partial dict; fields absent from it are left
    unchanged. This prevents stale full-object PUTs (e.g. a debounced
    panel-layout sync) from clobbering fields like
    ``enable_in_place_workspaces`` that a different code path just changed.
    """
    old_user_config = get_user_config_instance()

    for flag in _TELEMETRY_FLAGS:
        for key in (flag, to_camel(flag)):
            if key not in update_config_request.user_config:
                continue
            new_value = update_config_request.user_config[key]
            if new_value != getattr(old_user_config, flag):
                raise HTTPException(
                    status_code=400,
                    detail="Use POST /api/v1/config/telemetry to change telemetry consent.",
                )

    merged = old_user_config.model_dump(by_alias=True) if old_user_config else {}
    merged.update(update_config_request.user_config)
    new_user_config = UserConfig.model_validate(merged)

    save_config(new_user_config, get_config_path())
    set_user_config_instance(new_user_config)

    # Push updated dependencies status when dependency paths change so the
    # frontend atom reflects the new mode immediately.
    new_dep = new_user_config.dependency_paths
    old_dep = old_user_config.dependency_paths if old_user_config else None
    if new_dep != old_dep:
        services = get_services_from_request_or_websocket(request)
        services.dependency_management_service.get_status()

    return new_user_config


@router.post("/api/v1/config/telemetry")
def set_telemetry(
    set_telemetry_request: SetTelemetryRequest,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> UserConfig:
    """Flip the binary telemetry consent.

    This is the only endpoint allowed to change the underlying telemetry
    flags; PUT /api/v1/config rejects requests that would change them.
    """
    old_user_config = get_user_config_instance()
    new_user_config = model_update(
        old_user_config,
        get_privacy_settings_for_telemetry(set_telemetry_request.enabled).model_dump(),
    )
    save_config(new_user_config, get_config_path())
    set_user_config_instance(new_user_config)
    return new_user_config


@router.get("/api/v1/filesystem/list")
def list_directories(path: str = "~") -> list[DirectoryEntry]:
    """List directories at the given path for filesystem autocomplete.

    Used during onboarding when no project exists yet. Returns directories only,
    hides dotfiles unless the user explicitly types a dot prefix.
    """
    expanded = Path(path).expanduser()
    if not expanded.is_dir():
        parent = expanded.parent
        prefix = expanded.name.lower()
    else:
        parent = expanded
        prefix = ""

    if not parent.is_dir():
        return []

    results: list[DirectoryEntry] = []
    try:
        for entry in parent.iterdir():
            if not entry.is_dir():
                continue
            if prefix and not entry.name.lower().startswith(prefix):
                continue
            if entry.name.startswith(".") and not prefix.startswith("."):
                continue
            results.append(DirectoryEntry(name=entry.name, path=str(entry)))
    except PermissionError:
        return []

    results.sort(key=lambda r: r.name.lower())
    return results


@router.put("/api/v1/projects/{project_id}/workspace_setup_command")
def update_workspace_setup_command(
    project_id: str,
    request: Request,
    workspace_setup_command_request: WorkspaceSetupCommandRequest,
    user_session: UserSession = Depends(get_user_session),
) -> str | None:
    """Update the workspace setup command for a project.

    Tri-state: ``None`` resets to the current default, ``""`` explicitly disables
    the command, any other string is a user-customized command.
    """
    raw_command = workspace_setup_command_request.workspace_setup_command
    command_value = raw_command.strip() if raw_command is not None else None

    logger.info("Updating workspace setup command")
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        # SCU-474: targeted field-level update.  Writes only this field, so a
        # concurrent write to another project field can't be clobbered by a
        # stale full-object upsert.
        updated_project = transaction.update_project_fields(
            ProjectID(project_id), workspace_setup_command=command_value
        )
        if updated_project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    services.project_service.activate_project(updated_project)
    return updated_project.workspace_setup_command


@router.put("/api/v1/projects/{project_id}/naming_pattern")
def update_naming_pattern(
    project_id: str,
    request: Request,
    naming_pattern_request: NamingPatternRequest,
    user_session: UserSession = Depends(get_user_session),
) -> str | None:
    """Update the per-project branch-naming pattern override. Empty string clears the override."""
    raw = naming_pattern_request.naming_pattern
    trimmed = raw.strip() if raw else None
    pattern_value = trimmed if trimmed else None

    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        updated_project = transaction.update_project_fields(ProjectID(project_id), naming_pattern=pattern_value)
        if updated_project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    services.project_service.activate_project(updated_project)
    return updated_project.naming_pattern


@router.get("/api/v1/projects/{project_id}/files_and_folders")
def get_files_and_folders(
    project_id: str,
    request: Request,
    directory: str = "",
    filter: str = "",
    workspace_id: str | None = None,
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> list[str]:
    """List immediate contents of a directory in the project.

    When ``workspace_id`` is provided the listing is rooted at the workspace's
    working directory (e.g. a clone); otherwise it falls back to the project's
    local repo path.  Absolute ``directory`` values bypass the root and list
    the filesystem directly so users can reference files outside the repo.
    """
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(ProjectID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.organization_reference != user_session.organization_reference:
            raise HTTPException(status_code=403, detail="You do not have access to this project")

        root: Path | None = None
        if workspace_id is not None:
            validated_workspace_id = validate_workspace_id(workspace_id)
            workspace = transaction.get_workspace(validated_workspace_id)
            if workspace is None or workspace.is_deleted:
                raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
            root = services.workspace_service.get_workspace_working_directory(workspace, transaction)

        if root is None:
            root = project.get_local_user_path()

    try:
        entries = _list_directory_contents(root, directory)
        if filter:
            lower_filter = filter.lower()
            entries = [e for e in entries if lower_filter in e.lower()]
        return entries

    except Exception as e:
        log_exception(e, "Unexpected error getting files and folders")
        raise HTTPException(status_code=500, detail="Unexpected error getting files and folders") from e


def _list_directory_contents(repo_root: Path, directory: str) -> list[str]:
    """List immediate children of a directory, sorted with folders first.

    If ``directory`` is an absolute path it is used directly, bypassing
    ``repo_root``.  This lets users browse files outside the repository.
    """
    expanded = Path(directory).expanduser()
    target = expanded if expanded.is_absolute() else repo_root / directory
    if not target.is_dir():
        return []
    dirs: list[str] = []
    files: list[str] = []
    for entry in target.iterdir():
        if entry.is_dir():
            dirs.append(entry.name + "/")
        else:
            files.append(entry.name)
    dirs.sort()
    files.sort()
    return dirs + files


_REPO_ACCESS_MAX_RETRIES = 3
_REPO_ACCESS_RETRY_DELAY_SECONDS = 0.5
_GIT_INFO_TIMEOUT_SECONDS = 10


def _get_origin_url(repo_path: Path) -> str | None:
    """Get the origin remote URL for a repository, or None if not available."""
    try:
        result = run_blocking(
            ["git", "remote", "get-url", "origin"],
            timeout=_GIT_INFO_TIMEOUT_SECONDS,
            is_checked=False,
            cwd=repo_path,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _extract_hostname(url: str) -> str:
    """Extract hostname from a git remote URL (HTTPS, SSH, or SCP-style)."""
    # SCP-style: git@github.com:org/repo.git
    if ":" in url and not url.startswith(("https://", "http://", "ssh://")):
        return url.split("@", 1)[-1].split(":")[0]
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname or ""


def _is_gitlab_url(url: str) -> bool:
    """Check if a URL points to a GitLab instance."""
    return "gitlab" in _extract_hostname(url).lower()


def _is_github_url(url: str) -> bool:
    """Check if a URL points to a GitHub instance."""
    return "github" in _extract_hostname(url).lower()


def _get_remote_branches(repo_path: Path, remote_filter: str | None = "origin") -> list[str]:
    """Get remote branch names (e.g. 'origin/main').

    Args:
        repo_path: Path to the git repository.
        remote_filter: Only include branches from this remote (e.g. ``"origin"``).
            Pass ``None`` to include branches from all remotes.
    """
    try:
        result = subprocess.run(
            ["git", "branch", "-r", "--format=%(refname:short)"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=_GIT_INFO_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return []
        branches = []
        for line in result.stdout.strip().splitlines():
            branch = line.strip()
            if not branch:
                continue
            if remote_filter is not None and not branch.startswith(f"{remote_filter}/"):
                continue
            # Skip HEAD pointer entries
            if branch.endswith("/HEAD") or "HEAD ->" in line:
                continue
            branches.append(branch)
        return branches
    except (subprocess.TimeoutExpired, OSError):
        return []


@router.get("/api/v1/projects/{project_id}/current_branch")
def get_current_branch(
    project_id: ProjectID,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> CurrentBranchInfo:
    """Get just the current branch (fast endpoint)"""
    services = get_services_from_request_or_websocket(request)
    try:
        with user_session.open_transaction(services) as transaction:
            project = transaction.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            if not project.is_path_accessible:
                raise HTTPException(status_code=404, detail="Project path not accessible")

        # Retry git operations to handle transient failures (e.g. the repo is
        # momentarily in an unborn-branch state with no commits).
        current_branch: str | None = None
        for attempt in range(_REPO_ACCESS_MAX_RETRIES):
            with services.git_repo_service.open_local_user_git_repo_for_read(project, log_command=False) as repo:
                try:
                    current_branch = repo.get_current_git_branch()
                except FileNotFoundError as e:
                    raise HTTPException(status_code=500, detail=f"Could not find repository: {e}") from e
                except ProcessSetupError:
                    if project.is_path_accessible:
                        raise
                    raise HTTPException(status_code=404, detail="Project path has become inaccessible")
                except Exception:
                    if attempt < _REPO_ACCESS_MAX_RETRIES - 1:
                        time.sleep(_REPO_ACCESS_RETRY_DELAY_SECONDS)
                        continue
                    raise
                else:
                    break

        assert current_branch is not None
        return CurrentBranchInfo(current_branch=current_branch)
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        log_exception(e, "Failed to get current branch", priority=ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=404, detail="Failed to get current branch information")
    except Exception as e:
        log_exception(e, "Unexpected error getting current branch", priority=ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/v1/projects/{project_id}/branch-exists")
def branch_exists(
    project_id: str,
    name: str,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> BranchExistsResponse:
    """Return whether `name` already exists as a local branch in the project's repo."""
    validated_project_id = validate_project_id(project_id)
    services = get_services_from_request_or_websocket(request)

    trimmed = name.strip()
    if not trimmed:
        return BranchExistsResponse(exists=False)

    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(validated_project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        if not project.is_path_accessible:
            return BranchExistsResponse(exists=False)

    try:
        with services.git_repo_service.open_local_user_git_repo_for_read(project, log_command=False) as repo:
            return BranchExistsResponse(exists=repo.is_branch_ref(trimmed))
    except FileNotFoundError:
        return BranchExistsResponse(exists=False)


@router.get("/api/v1/projects/{project_id}/repo_info")
def get_repo_info(
    project_id: ProjectID,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> RepoInfo:
    """Get repository information including path and recent branches"""
    services = get_services_from_request_or_websocket(request)
    try:
        with user_session.open_transaction(services) as transaction:
            project = transaction.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            if not project.is_path_accessible:
                raise HTTPException(status_code=404, detail="Project path not accessible")

        # Retry git operations to handle transient failures (e.g. the repo is
        # momentarily in an unborn-branch state with no commits).
        repo_path: Path | None = None
        branches: list[str] | None = None
        current_branch: str | None = None
        for attempt in range(_REPO_ACCESS_MAX_RETRIES):
            with services.git_repo_service.open_local_user_git_repo_for_read(project, log_command=False) as repo:
                repo_path = repo.get_repo_path()
                try:
                    branches = repo.get_all_branches()
                    current_branch = repo.get_current_git_branch()
                except FileNotFoundError as e:
                    raise HTTPException(status_code=500, detail=f"Could not find repository: {e}") from e
                except ProcessSetupError:
                    # The is_path_accessible attribute is set in _check_and_update_project_accessibility, which
                    # used to fail when the project repo is a remote mounted directory which got disconnected.
                    # Properly catching the OSError there should prevent an unnecessary re-raise here, preventing
                    # Sentry spam and hopefully preventing the backend from crashing.
                    if project.is_path_accessible:
                        raise
                    raise HTTPException(status_code=404, detail=f"Project path {repo_path} has become inaccessible")
                except Exception:
                    if attempt < _REPO_ACCESS_MAX_RETRIES - 1:
                        time.sleep(_REPO_ACCESS_RETRY_DELAY_SECONDS)
                        continue
                    raise
                else:
                    break

        assert repo_path is not None and branches is not None and current_branch is not None

        if not branches:
            raise HTTPException(status_code=500, detail=f"Could not find any branches in repository {repo_path}")

        # Get origin URL and provider detection info
        origin_url = _get_origin_url(repo_path)
        is_gitlab_origin = _is_gitlab_url(origin_url) if origin_url is not None else False
        is_github_origin = _is_github_url(origin_url) if origin_url is not None else False
        remote_branches = _get_remote_branches(repo_path)

        return RepoInfo(
            repo_path=repo_path,
            current_branch=current_branch,
            recent_branches=branches,
            project_id=project.object_id,
            is_gitlab_origin=is_gitlab_origin,
            is_github_origin=is_github_origin,
            remote_branches=remote_branches,
        )
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        log_exception(e, "Failed to get repo info", priority=ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=500, detail="Failed to get repository information")
    except Exception as e:
        log_exception(e, "Unexpected error getting repo info", priority=ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=500, detail=str(e))


@APP.websocket("/api/v1/stream/ws")
async def stream_everything_websocket(
    websocket: WebSocket,
    user_session: UserSession = Depends(get_user_session_for_websocket),
    shutdown_event: Event = Depends(shutdown_event_impl),
    scope: Scope = Depends(resolve_stream_scope),
) -> None:
    """Unified stream for all updates: tasks, task details, user data, notifications.

    Streams for ALL projects and ALL tasks for the authenticated user.
    """
    services = get_services_from_request_or_websocket(websocket)
    root_concurrency_group = get_root_concurrency_group(websocket)
    with root_concurrency_group.make_concurrency_group(name="stream_everything_websocket") as stream_concurrency_group:
        await to_websocket_stream(
            user_session,
            stream_everything(
                user_session=user_session,
                scope=scope,
                shutdown_event=shutdown_event,
                services=services,
                concurrency_group=stream_concurrency_group,
                dependency_management_service=services.dependency_management_service,
                pr_polling_service=services.pr_polling_service,
                btw_service=services.btw_service,
            ),
            websocket,
            stream_concurrency_group.shutdown_event,
        )


@router.delete("/api/v1/workspaces/{workspace_id}/terminal/{index}")
def close_workspace_terminal(
    workspace_id: str,
    index: int,
    request: Request,
) -> Response:
    """Stop the pty + shell for the given workspace terminal index.

    Distinct from WebSocket disconnect: closing the WebSocket preserves the
    pty so the terminal can be reconnected. This route is for explicit user
    "close this terminal" actions (the panel X button) -- it tears down the
    shell, closes the primary fd, and removes the terminal from the registry.
    """
    validated_workspace_id = validate_workspace_id(workspace_id)
    services = get_services_from_request_or_websocket(request)
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        workspace = transaction.get_workspace(validated_workspace_id)
    if workspace is None or workspace.environment_id is None:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
    terminal_id = make_terminal_id(workspace.environment_id, index)
    manager = unregister_terminal_manager(terminal_id)
    if manager is None:
        raise HTTPException(status_code=404, detail=f"Terminal {index} not found for workspace {workspace_id}")
    manager.stop()
    return Response(status_code=204)


@APP.websocket("/api/v1/workspaces/{workspace_id}/terminal/{index}/ws")
async def workspace_terminal_websocket(
    websocket: WebSocket,
    workspace_id: str,
    index: int,
) -> None:
    """WebSocket endpoint for terminal connections, routed by workspace ID and terminal index.

    Looks up the workspace's environment_id, derives the terminal_id from the
    environment_id and index, and connects the WebSocket to the pty. Terminal
    index 0 is the default terminal created at workspace startup; higher indices
    are created lazily on first connection.
    """
    services = get_services_from_request_or_websocket(websocket)
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        workspace = transaction.get_workspace(WorkspaceID(workspace_id))
    if workspace is None or workspace.environment_id is None:
        # Accept the WebSocket before closing so the client receives the 4404
        # close code as a proper WebSocket close frame.  Without accept(),
        # Starlette returns an HTTP 403, which the browser surfaces as close
        # code 1006 — preventing the frontend's 4404-based retry logic from
        # triggering.
        await websocket.accept()
        await websocket.close(code=4404, reason=f"Workspace {workspace_id} not found or has no environment")
        return

    environment_id = workspace.environment_id
    terminal_id = make_terminal_id(environment_id, index)
    terminal_manager = get_terminal_manager(terminal_id)

    # On-demand creation: the default terminal (index 0) is normally created
    # eagerly at workspace startup, but if that failed, it can be created here
    # on first connection. Additional terminals (index > 0) are always created
    # lazily on first connection.
    if terminal_manager is None:
        terminal_manager = create_terminal_for_environment(environment_id, index)

    if terminal_manager is not None:
        await _connect_terminal_websocket(websocket, terminal_id)
        return

    await websocket.accept()
    await websocket.close(code=4404, reason=f"Terminal {index} not found for workspace {workspace_id}")


async def _connect_terminal_websocket(websocket: WebSocket, terminal_id: str) -> None:
    """Connect a WebSocket to a terminal's pty.

    Shared implementation for both workspace-based and terminal-ID-based routes.
    Data is relayed bidirectionally between the WebSocket and the pty.
    The pty stays alive when the WebSocket disconnects, preserving the terminal session.
    """
    logger.debug("Terminal WebSocket connection requested for terminal {}", terminal_id)

    terminal_manager = get_terminal_manager(terminal_id)
    if terminal_manager is None:
        logger.warning("Terminal not found for terminal {}", terminal_id)
        # Accept first so the client receives a proper 4404 WebSocket close
        # frame (see workspace_terminal_websocket for the full explanation).
        await websocket.accept()
        await websocket.close(code=4404, reason=f"Terminal not found for terminal {terminal_id}")
        return

    logger.debug("Found terminal manager for terminal {}", terminal_id)
    await websocket.accept()

    # Set up output callback to forward pty output to WebSocket.
    # asyncio.Queue is NOT thread-safe, so the callback (called from the PTY
    # reader thread) must use call_soon_threadsafe to properly wake the event
    # loop. Without this, the event loop may not process queued data until its
    # next iteration, adding up to 100ms+ of latency per keystroke echo.
    loop = asyncio.get_running_loop()
    output_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_output(data: bytes) -> None:
        try:
            loop.call_soon_threadsafe(output_queue.put_nowait, data)
        except RuntimeError:
            pass  # Event loop closed

    try:
        # Atomically snapshot the buffer AND register the callback.  Doing these
        # as two separate calls leaves a window in which the pty reader thread
        # can append bytes to the buffer that are never sent to this client — the
        # buffer snapshot misses them (they arrived after it was taken) and the
        # callback misses them (it wasn't registered yet).  Bash's initial prompt
        # echo plus a fast setup command can fit entirely inside that window
        # under CI load, which is what was causing
        # test_setup_command_does_not_rerun_… to flake with an empty xterm buffer.
        #
        # This must be inside the try whose finally removes the callback:
        # otherwise a disconnect between registering and the first send_bytes
        # below leaks the callback (it stays subscribed to the manager forever).
        buffered_output = terminal_manager.subscribe(on_output)
        logger.debug(
            "Sending {} bytes of buffered output for terminal {}",
            len(buffered_output),
            terminal_id,
        )
        if buffered_output:
            await websocket.send_bytes(buffered_output)

        # These handlers are terminal-specific (resize commands, pty forwarding)
        # and defined inline as they capture local state (terminal_manager, output_queue)
        async def read_websocket() -> None:
            try:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if "bytes" in message:
                        terminal_manager.write(message["bytes"])
                    elif "text" in message:
                        # Handle text messages (e.g., resize commands)
                        try:
                            data = json.loads(message["text"])
                            if data.get("type") == "resize":
                                terminal_manager.resize(data["rows"], data["cols"])
                        except (json.JSONDecodeError, KeyError):
                            # Treat as regular text input
                            terminal_manager.write(message["text"].encode())
            except WebSocketDisconnect:
                pass

        async def write_websocket() -> None:
            try:
                while True:
                    # Wait for the first chunk, then drain any additional pending
                    # chunks and send them as a single WebSocket message. This
                    # batching reduces per-message overhead during burst output
                    # (e.g., `cat large_file`) without adding latency for
                    # interactive typing.
                    data = await output_queue.get()
                    chunks = [data]
                    while not output_queue.empty():
                        try:
                            chunks.append(output_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break
                    await websocket.send_bytes(b"".join(chunks))
            except WebSocketDisconnect:
                pass
            except Exception:
                pass  # Connection closed

        # Run both tasks concurrently.
        # Note: asyncio.create_task is not common in our codebase (we prefer threads for
        # debuggability), but it's appropriate here for WebSocket bidirectional streaming.
        read_task = asyncio.create_task(read_websocket())
        write_task = asyncio.create_task(write_websocket())

        # Wait for read task to complete (WebSocket disconnect)
        await read_task
        write_task.cancel()
        try:
            await write_task
        except asyncio.CancelledError:
            pass

    finally:
        terminal_manager.remove_output_callback(on_output)


async def _try_to_gracefully_close_on_error(websocket: WebSocket, error: SerializedException) -> None:
    try:
        await websocket.send_json(model_dump(error, is_camel_case=True))
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.info("Failed to send WebSocket error message to client: {}", e)

    try:
        await websocket.close(code=1011, reason="Internal Server Error")
    except Exception as e:
        logger.info("Failed to gracefully close websocket after error: {}", e)
        return


async def to_websocket_stream(
    user_session: UserSession,
    generator: Generator[UpdateT | None, None, None],
    websocket: WebSocket,
    close_event: MutableEvent,
) -> None:
    try:
        await websocket.accept()
    except RuntimeError as e:
        # suppressing this when we are shutting down, doesn't seem to matter
        if (
            "Expected ASGI message 'websocket.send' or 'websocket.close', but got 'websocket.accept'" in str(e)
            and hasattr(APP, "shutdown_event")
            and APP.shutdown_event.is_set()
        ):
            with logger.contextualize(**user_session.logger_kwargs):
                error = SerializedException.build(e)
            await _try_to_gracefully_close_on_error(websocket, error)
        else:
            raise
    try:
        itr = iter(generator)
        while True:
            loop = asyncio.get_event_loop()
            to_yield = await loop.run_in_executor(
                None,
                run_sync_function_with_debugging_support_if_enabled,
                _get_next_elem_for_websocket,
                (itr, user_session),
                {},
            )
            if to_yield is None:
                with logger.contextualize(**user_session.logger_kwargs):
                    logger.debug("Stream ended normally.")
                    await websocket.close(code=1000, reason="Stream ended normally")
                    return
            await websocket.send_json(to_yield)
            await asyncio.sleep(0.00001)
    except ServerStopped:
        with logger.contextualize(**user_session.logger_kwargs):
            logger.debug("Server is stopping, closing update stream.")
            await websocket.close(code=1001, reason="Server is stopping")
            return
    except WebSocketDisconnect:
        with logger.contextualize(**user_session.logger_kwargs):
            logger.debug("WebSocket client disconnected")
        return
    except TaskNotFound as e:
        with logger.contextualize(**user_session.logger_kwargs):
            log_exception(e, "Task not found", priority=ExceptionPriority.LOW_PRIORITY)
            error = SerializedException.build(e)
        await _try_to_gracefully_close_on_error(websocket, error)
        raise
    except CancelledError as e:
        error = SerializedException.build(e)
        await _try_to_gracefully_close_on_error(websocket, error)
    except BaseException as e:
        with logger.contextualize(**user_session.logger_kwargs):
            log_exception(
                e,
                "Error in event stream generator",
                priority=ExceptionPriority.MEDIUM_PRIORITY,
            )
            error = SerializedException.build(e)
        await _try_to_gracefully_close_on_error(websocket, error)
        raise
    finally:
        close_event.set()
        generator.close()


def _get_next_elem_for_websocket(
    itr: Iterator[UpdateT | None], user_session: UserSession
) -> str | dict[str, Any] | None:
    with logger.contextualize(**user_session.logger_kwargs):
        try:
            entry = next(itr)
            # Do not raise StopIteration from this function as it cannot be properly propagated through the executor boundary.
        except StopIteration:
            return None
        if entry is None:
            to_yield = "null"
        else:
            to_yield = entry.model_dump(mode="json", by_alias=True)
        return to_yield


def _get_artifact_data(
    artifact_name: str,
    services: CompleteServiceCollection,
    task_id_str: str,
    user_session: UserSession,
) -> str:
    try:
        task_id = TaskID(task_id_str)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["path", "task_id"], "msg": "Invalid task ID format", "type": "value_error"}],
        ) from e
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(task_id, transaction)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    # Backfill from the workspace's stable artifacts dir if the cache was wiped
    # (SCU-1245); returns False only when no snapshot exists anywhere.
    if not services.task_service.ensure_artifact_cache_populated(task_id, artifact_name):
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact_data_url = services.task_service.get_artifact_file_url(task_id, artifact_name)
    assert str(artifact_data_url).startswith("file://"), "Only local file artifacts are supported"
    artifact_data_path = Path(str(artifact_data_url).replace("file://", ""))
    if not artifact_data_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact_data = artifact_data_path.read_text(encoding="utf-8")
    logger.debug("Returning artifact at path {}", artifact_data_path)
    return artifact_data


def _get_typed_artifact_data(
    artifact_name: str,
    services: CompleteServiceCollection,
    task_id_str: str,
    user_session: UserSession,
) -> ArtifactDataResponse:
    """Get artifact data and return it with proper typing based on artifact type."""
    raw_data = _get_artifact_data(artifact_name, services, task_id_str, user_session)
    try:
        _artifact_type = ArtifactType(artifact_name)
    except ValueError as e:
        logger.error("Unknown artifact type: {}", artifact_name)
        raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_name}") from e

    # happens occasionally, better to do this than cause flaky test errors
    if raw_data == "":
        raise HTTPException(status_code=404, detail="Artifact is empty")

    try:
        parsed_json = json.loads(raw_data)

        if not isinstance(parsed_json, dict) or "object_type" not in parsed_json:
            logger.error("Artifact missing object_type field: {}", artifact_name)
            raise HTTPException(status_code=500, detail="Invalid artifact format")

        object_type = parsed_json["object_type"]
        version = parsed_json.get("version")

        if object_type == "TaskListArtifact" and version == 2:
            return TaskListArtifact.model_validate(parsed_json)
        if object_type == "TaskListArtifact":
            logger.info(
                "TaskListArtifact with unsupported version {} for {}; returning empty",
                version,
                artifact_name,
            )
            return TaskListArtifact(tasks=[])
        if object_type == "TodoListArtifact":
            logger.info(
                "Legacy TodoListArtifact on disk for {}; returning empty TaskListArtifact",
                artifact_name,
            )
            return TaskListArtifact(tasks=[])
        if object_type == "DiffArtifact":
            return DiffArtifact.model_validate(parsed_json)
        logger.error("Unknown object_type: {}", object_type)
        raise HTTPException(
            status_code=500,
            detail=f"Unknown artifact object_type: {object_type}",
        )

    except json.JSONDecodeError as e:
        log_exception(
            e,
            "Failed to parse artifact JSON",
            priority=ExceptionPriority.MEDIUM_PRIORITY,
        )
        raise HTTPException(status_code=500, detail="Invalid artifact JSON") from e
    except ValidationError as e:
        log_exception(
            e,
            "Failed to validate artifact data",
            priority=ExceptionPriority.MEDIUM_PRIORITY,
        )
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": "Invalid artifact data", "type": "value_error"}],
        ) from e


@router.get("/api/v1/health")
def get_health_check(request: Request) -> HealthCheckResponse:
    services = get_services_from_request_or_websocket(request)
    user_config = get_user_config_instance()
    free_gb = (_get_disk_bytes_free(services.settings) or 1_000_000_000_000) / (1024 * 1024 * 1024)

    # pyre-fixme[16]: CompleteServiceCollection.data_model_service is TaskDataModelService at runtime
    with services.data_model_service.open_task_transaction() as transaction:
        active_task_count = len(transaction.get_active_tasks())

    dependencies_status = services.dependency_management_service.get_status()

    return HealthCheckResponse(
        version=str(version.__version__),
        git_sha=str(version.__git_sha__),
        python_version=sys.version.split()[0],
        platform=platform.system(),
        platform_version=platform.release(),
        free_disk_gb=free_gb,
        min_free_disk_gb=user_config.min_free_disk_gb if user_config else 0,
        free_disk_gb_warn_limit=user_config.free_disk_gb_warn_limit if user_config else 0,
        uptime_seconds=time.time() - _SERVER_START_TIME,
        active_task_count=active_task_count,
        data_directory=str(build_utils.get_sculptor_folder()),
        install_mode="packaged" if is_packaged() else "source",
        install_path=str(get_install_path()),
        ci_job_id=version.ci_job_id,
        ci_ref=version.ci_ref,
        dependencies_status=dependencies_status,
    )


@router.get("/api/v1/projects/most-recently-used")
def get_most_recently_used_project() -> ProjectID | None:
    return get_most_recently_used_project_id()


@router.delete("/api/v1/projects/{project_id}")
def delete_project(
    project_id: ProjectID,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Mark a project as deleted."""
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        # NOTE: we are unable to delete tasks from inside project service because it doesn't have access to task service
        assert isinstance(transaction, TaskAndDataModelTransaction)
        tasks = transaction.get_tasks_for_project(project_id=project_id)
        active_tasks = [task for task in tasks if not task.is_deleting and not task.is_deleted]
        logger.info("Deleting {} tasks for project {}", len(active_tasks), project_id)
        for task in active_tasks:
            services.task_service.delete_task(task.object_id, transaction)
        logger.info("Successfully deleted {} tasks for project {}", len(active_tasks), project_id)
        # Delete all workspaces belonging to this project
        workspaces = transaction.get_workspaces(project_id=project_id)
        logger.info("Deleting {} workspaces for project {}", len(workspaces), project_id)
        for workspace in workspaces:
            services.workspace_service.delete_workspace(workspace.object_id, transaction)
        logger.info("Successfully deleted {} workspaces for project {}", len(workspaces), project_id)
        logger.info("Deleting project {}", project_id)
        services.project_service.delete_project(project, transaction)
        logger.info("Successfully deleted project {}", project_id)


@router.get("/api/v1/projects/active")
def get_active_projects(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> tuple[Project, ...]:
    """Get all currently active projects for the session."""

    services = get_services_from_request_or_websocket(request)
    return services.project_service.get_active_projects()


@router.post("/api/v1/projects/initialize")
def initialize_project(
    request: Request,
    initialization_request: ProjectInitializationRequest,
    user_session: UserSession = Depends(get_user_session),
) -> Project:
    project_path = Path(initialization_request.project_path).expanduser()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Project path is not a directory: {project_path}")

    if not (project_path / ".git").exists():
        if is_path_in_git_repo(project_path):
            raise HTTPException(
                status_code=400,
                detail="Selected directory is inside a git repository. Please select the root of the git repository.",
            )
        raise HTTPException(
            status_code=400,
            detail="Selected directory is not a git repository. Please initialize it first using /api/v1/projects/init-git",
        )

    # If the path is a worktree, register the parent repo instead. The parent
    # is the canonical repository — registering a worktree aliases the same
    # repo by a different path, and downstream operations like
    # ``git clone --reference`` reject worktrees outright.
    canonical_path = resolve_worktree_to_main_repo(project_path)
    if canonical_path != project_path:
        logger.info(
            "Resolved worktree path {} to main repo {} for project registration",
            project_path,
            canonical_path,
        )
        project_path = canonical_path

    # ensure we have an initial commit, and if not, offer to create one
    root_concurrency_group = get_root_concurrency_group(request)
    with root_concurrency_group.make_concurrency_group(name="initialize_project") as concurrency_group:
        check_repo = LocalReadOnlyGitRepo(repo_path=project_path, concurrency_group=concurrency_group)
        is_initial_commit_present = check_repo.has_any_commits()

    if not is_initial_commit_present:
        raise HTTPException(
            status_code=409,
            detail="Selected git repository has no commits. Please create an initial commit first.",
        )

    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        # Check if this repo path is already registered
        existing_projects = transaction.get_projects(user_session.organization_reference)
        absolute_path = project_path.absolute()
        for existing_project in existing_projects:
            if existing_project.user_git_repo_url is None:
                continue
            if Path(existing_project.get_local_user_path()).absolute() == absolute_path:
                raise HTTPException(
                    status_code=409,
                    detail="This repository is already added to Sculptor.",
                )

        project = services.project_service.initialize_project(
            project_path=project_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
        services.project_service.activate_project(project)
    return project


@router.get("/api/v1/projects")
def list_projects(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> tuple[Project, ...]:
    services = get_services_from_request_or_websocket(request)
    with user_session.open_transaction(services) as transaction:
        return transaction.get_projects(organization_reference=user_session.organization_reference)


def _display_path(path: Path) -> str:
    """Replace the user's home directory with ~ for display."""
    home = Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


@router.get("/api/v1/env-var-names")
def get_env_var_names(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> EnvVarNamesResponse:
    """Read environment variable names from global and per-project .env files on disk."""
    sculptor_folder = get_sculptor_folder()
    global_env_path = sculptor_folder / ".env"
    global_var_names = tuple(parse_env_file(global_env_path).keys())

    services = get_services_from_request_or_websocket(request)
    project_entries: list[ProjectEnvVarNames] = []
    with user_session.open_transaction(services) as transaction:
        projects = transaction.get_projects(organization_reference=user_session.organization_reference)
    for project in projects:
        if project.is_deleted or not project.is_path_accessible or project.user_git_repo_url is None:
            continue
        project_path = project.get_local_user_path()
        env_file = project_path / ".sculptor" / ".env"
        if not env_file.exists():
            continue
        var_names = tuple(parse_env_file(env_file).keys())
        if var_names:
            project_entries.append(
                ProjectEnvVarNames(
                    project_name=project.name,
                    project_path=_display_path(project_path),
                    var_names=var_names,
                )
            )

    return EnvVarNamesResponse(
        global_var_names=global_var_names,
        global_env_path=_display_path(global_env_path),
        projects=tuple(project_entries),
    )


@router.post("/api/v1/projects/init-git")
def initialize_git_repository(
    request: Request,
    init_git_repo_request: InitializeGitRepoRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Initialize a directory as a git repository with an initial commit."""
    project_path = Path(init_git_repo_request.project_path).expanduser()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Project path is not a directory: {project_path}")
    if (project_path / ".git").exists():
        raise HTTPException(status_code=400, detail=f"Directory is already a git repository: {project_path}")

    logger.info("Initializing git repository at: {}", project_path)

    root_concurrency_group = get_root_concurrency_group(request)
    initialization_error: Exception | None = None
    with root_concurrency_group.make_concurrency_group(name="initialize_git_repository") as concurrency_group:
        try:
            # Initialize repository (using global git config for user.email and user.name)
            repo = LocalWritableGitRepo.from_new_repository(
                repo_path=project_path, concurrency_group=concurrency_group
            )
            repo.create_commit("Initial commit", allow_empty=True)
        except (GitRepoError, Exception) as e:
            log_exception(e, "Failed to initialize git repository")
            initialization_error = e

    if initialization_error is not None:
        error_msg = str(initialization_error)
        stderr = getattr(initialization_error, "stderr", None)
        if stderr:
            error_msg = str(stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize git repository: {error_msg}",
        ) from initialization_error


@router.post("/api/v1/projects/create-initial-commit")
def create_initial_commit(
    request: Request,
    create_initial_commit_request: CreateInitialCommitRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    project_path = Path(create_initial_commit_request.project_path).expanduser()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Project path is not a directory: {project_path}")

    logger.info("Creating initial commit in git repository at: {}", project_path)

    root_concurrency_group = get_root_concurrency_group(request)
    initialization_error: Exception | None = None
    with root_concurrency_group.make_concurrency_group(name="create_initial_commit") as concurrency_group:
        try:
            repo = LocalWritableGitRepo(repo_path=project_path, concurrency_group=concurrency_group)
            repo.stage_all_files()
            repo.create_commit("Initial commit", allow_empty=True)
        except (GitRepoError, Exception) as e:
            initialization_error = e
            log_exception(e, "Failed to create initial commit")
    if initialization_error is not None:
        error_msg = str(initialization_error)
        stderr = getattr(initialization_error, "stderr", None)
        if stderr:
            error_msg = str(stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create initial commit: {error_msg}",
        ) from initialization_error


@router.post("/api/v1/open-path-in-app")
def open_path_in_app(
    open_path_in_app_request: OpenPathInAppRequest,
    user_session: UserSession = Depends(get_user_session),
) -> OpenPathInAppResult:
    """Open a file system path in an external application."""
    target_path = Path(open_path_in_app_request.path).expanduser()
    return open_path_in_external_app(open_path_in_app_request.app, target_path)


MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20MB


@router.post("/api/v1/upload-file")
def upload_file(
    file: UploadFile = FastAPIFile(...),
    user_session: UserSession = Depends(get_user_session),
) -> UploadFileResponse:
    """Accept a multipart file upload and store it in the backend upload directory."""
    content = file.file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum size of 20MB")

    original_ext = Path(file.filename or "").suffix
    file_id = f"{uuid4()}{original_ext}"

    settings = get_settings()
    upload_dir = settings.upload_path
    os.makedirs(upload_dir, exist_ok=True)
    (upload_dir / file_id).write_bytes(content)

    return UploadFileResponse(file_id=file_id)


@router.get("/api/v1/uploaded-file/{file_id}")
def get_uploaded_file(
    file_id: str,
    user_session: UserSession = Depends(get_user_session),
) -> FileResponse:
    """Serve a previously uploaded file by its file_id."""
    settings = get_settings()
    upload_dir = settings.upload_path.resolve()
    file_path = (upload_dir / file_id).resolve()
    if not file_path.is_relative_to(upload_dir):
        raise HTTPException(status_code=400, detail="Invalid file_id")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)


@router.post("/api/v1/upload-diagnostics")
def upload_diagnostics(
    request_body: UploadDiagnosticsRequest,
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> UploadDiagnosticsResponse:
    """Bundle diagnostic data and logs into a zip, upload to S3, and return the report ID."""
    settings = get_settings()
    services = get_services_from_request_or_websocket(request)
    return perform_upload_diagnostics(
        request_body=request_body,
        settings=settings,
        server_start_time=_SERVER_START_TIME,
        dependency_management_service=services.dependency_management_service,
    )


class TraceBatchRequest(SerializableModel):
    """Batch of Chrome-JSON trace events from a non-backend source.

    The ``source`` field selects the synthetic ``pid`` the events are tagged
    with so that the backend's, the renderer's, and Electron-main's events
    appear as separate processes in the Perfetto UI.
    """

    source: Literal["renderer", "electron_main"]
    events: list[dict[str, Any]]


_TRACE_SOURCE_TO_PID = {
    "renderer": RENDERER_PID,
    "electron_main": ELECTRON_MAIN_PID,
}


@router.post("/api/v1/trace/batch", status_code=204)
def post_trace_batch(payload: TraceBatchRequest) -> None:
    """Buffer a batch of Chrome-JSON trace events from the renderer or the
    Electron main process. Silently no-ops when tracing is not enabled — the
    frontend / Electron main are responsible for checking that flag before
    POSTing, but we double-check here to be safe."""
    if not is_tracing_enabled():
        return
    add_external_events(payload.events, _TRACE_SOURCE_TO_PID[payload.source])


# Dummy routes to include WebSocket types in OpenAPI schema


@router.get("/_ws_types/streaming_update")
def _ws_type_streaming_update() -> StreamingUpdate:
    """Include StreamingUpdate in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


# we generate UserConfigField at runtime so pyre doesn't like it as an annotation
@router.get("/_types/user_config_field")
def _type_user_config_field() -> UserConfigField:  # pyre-ignore[11]
    """Include UserConfigField enum in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


@router.get("/_element_tags")
def _element_tags() -> ElementIDs:
    """Include UserUpdate in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


APP.include_router(router)

# pyre doesn't understand the typing here
APP.add_middleware(SessionTokenMiddleware, settings_factory=get_settings)  # pyre-ignore[6]


# TODO (PROD-2161): either we can remove this or leave it for debugging, it might fail depending on what we change with the build process
# To avoid conflicts with the API routes, we write this route last. This route
# must be loaded _after_ APP.include_router, which performs delayed routing.
@APP.get("/{filename:path}")
def serve_static(filename: str = "index.html") -> Response:
    """Serve the static files from frontend-dist, serving "index.html" when no filename is provided"""
    try:
        response = _load_file(filename, resources.files("sculptor") / ".." / "frontend-dist")
    except FileNotFoundError:
        try:
            # try this path instead, is helpful for being able to sensibly run tests locally...
            response = _load_file(filename, resources.files("sculptor") / ".." / "frontend" / "dist")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"File not found: {filename}") from e
    return response


def _load_file(filename: str, static_dir: Traversable) -> Response:
    if not filename:
        filename = "index.html"

    initial_file_path = static_dir / filename

    with resources.as_file(initial_file_path) as resolved_initial_file_path:
        if not resolved_initial_file_path.exists():
            # If we don't have the url, return the home page since this is a
            # single-page webapp. The React router should parse the url to
            # render the correct "synthetic" page.
            final_file_path = static_dir / "index.html"
        else:
            final_file_path = initial_file_path

    with resources.as_file(final_file_path) as resolved_final_file_path:
        mime_type, _ = mimetypes.guess_type(resolved_final_file_path)
        # For the SPA's index.html we inject a global so the renderer learns
        # synchronously at boot whether tracing is on, with no first-load gap
        # waiting on a separate fetch.
        if resolved_final_file_path.name == "index.html":
            html_bytes = resolved_final_file_path.read_bytes()
            html_bytes = _inject_tracing_flag(html_bytes)
            return Response(
                content=html_bytes,
                media_type=mime_type or "text/html",
                headers={"Content-Length": str(len(html_bytes))},
            )
        return StreamingResponse(
            create_file_generator(resolved_final_file_path),
            media_type=mime_type,
            headers={"Content-Length": str(resolved_final_file_path.stat().st_size)},
        )


_TRACING_INJECTION_SCRIPT_TEMPLATE = b"<script>window.__SCULPTOR_TRACING__ = {enabled: %s};</script>"


def _inject_tracing_flag(html: bytes) -> bytes:
    """Inject ``window.__SCULPTOR_TRACING__`` right after ``<head>`` so the
    renderer can read it synchronously at boot."""
    enabled_literal = b"true" if is_tracing_enabled() else b"false"
    script = _TRACING_INJECTION_SCRIPT_TEMPLATE % enabled_literal
    # Match the opening <head> tag (case-insensitive, allow attributes).
    pattern = re.compile(rb"<head\b[^>]*>", re.IGNORECASE)
    match = pattern.search(html)
    if match is None:
        # If there is no <head>, fall through unmodified rather
        # than corrupting the HTML.
        return html
    insert_at = match.end()
    return html[:insert_at] + script + html[insert_at:]


def create_file_generator(file_path: Path) -> Generator[bytes, None, None]:
    with open(file_path, "rb") as f:
        chunk = f.read(8192)
        while chunk:
            yield chunk
            chunk = f.read(8192)


def _get_disk_bytes_free(settings: SculptorSettings) -> int | None:
    db_path = Path(settings.DATABASE_URL.split("sqlite:///")[-1])
    if not db_path.exists():
        return None
    return psutil.disk_usage(str(db_path)).free
