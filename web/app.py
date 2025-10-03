import asyncio
import contextlib
import hashlib
import json
import logging
import mimetypes
import queue
import subprocess
import time
from asyncio import CancelledError
from datetime import datetime
from datetime import timedelta
from importlib import resources
from pathlib import Path
from threading import Event
from typing import Generator
from typing import TypeVar
from urllib.parse import urlencode
from urllib.parse import urljoin

import httpx
import requests
import sentry_sdk
import typeid.errors
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse
from fastapi.websockets import WebSocket
from fastapi.websockets import WebSocketDisconnect
from loguru import logger
from pydantic import ValidationError

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TypeIDPrefixMismatchError
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.git import is_path_in_git_repo
from imbue_core.itertools import only
from imbue_core.nested_evolver import assign
from imbue_core.nested_evolver import chill
from imbue_core.nested_evolver import evolver
from imbue_core.processes.local_process import run_blocking
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import model_dump
from imbue_core.pydantic_serialization import model_dump_json
from imbue_core.pydantic_utils import model_update
from imbue_core.s3_uploader import upload_to_s3
from imbue_core.sculptor import telemetry
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.sculptor.user_config import UserConfig
from imbue_core.sculptor.user_config import UserConfigField
from imbue_core.serialization import SerializedException
from imbue_core.subprocess_utils import ProcessError
from sculptor import version
from sculptor.config.anthropic_oauth import AnthropicAccountType
from sculptor.config.anthropic_oauth import cancel_anthropic_oauth as cancel_anthropic_oauth_impl
from sculptor.config.anthropic_oauth import start_anthropic_oauth as start_anthropic_oauth_impl
from sculptor.config.settings import SculptorSettings
from sculptor.config.telemetry_info import get_onboarding_telemetry_info
from sculptor.config.telemetry_info import get_telemetry_info as get_telemetry_info_impl
from sculptor.config.user_config import create_organization_id
from sculptor.config.user_config import create_user_id
from sculptor.config.user_config import get_config_path
from sculptor.config.user_config import get_default_user_config_instance
from sculptor.config.user_config import get_user_config_instance
from sculptor.config.user_config import save_config
from sculptor.config.user_config import set_user_config_instance
from sculptor.config.user_config import update_user_consent_level
from sculptor.constants import ElementIDs
from sculptor.constants import GatewayRemoteAPIEndpoints
from sculptor.constants import SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import FixID
from sculptor.database.models import FixRequest
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import AgentMessageID
from sculptor.interfaces.agents.v1.agent import AgentSnapshotRunnerMessage
from sculptor.interfaces.agents.v1.agent import ArtifactType
from sculptor.interfaces.agents.v1.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.v1.agent import ClaudeCodeTextAgentConfig
from sculptor.interfaces.agents.v1.agent import CommandInputUserMessage
from sculptor.interfaces.agents.v1.agent import CompactTaskUserMessage
from sculptor.interfaces.agents.v1.agent import EphemeralRequestCompleteAgentMessage
from sculptor.interfaces.agents.v1.agent import ForkAgentSystemMessage
from sculptor.interfaces.agents.v1.agent import GitCommitAndPushUserMessage
from sculptor.interfaces.agents.v1.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.v1.agent import ManualSyncMergeIntoAgentAttemptedMessage
from sculptor.interfaces.agents.v1.agent import ManualSyncMergeIntoUserAttemptedMessage
from sculptor.interfaces.agents.v1.agent import PersistentMessageTypes
from sculptor.interfaces.agents.v1.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.v1.agent import RemoveQueuedMessageUserMessage
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.interfaces.agents.v1.agent import UpdateSystemPromptUserMessage
from sculptor.interfaces.agents.v1.agent import UsageArtifact
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.interfaces.environments.v1.base import LocalDevcontainerImageConfig
from sculptor.interfaces.environments.v1.base import LocalDockerEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.primitives.constants import USER_FACING_LOG_TYPE
from sculptor.primitives.ids import UserReference
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.configuration_broadcast_service.api import ProjectConfiguration
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    get_devcontainer_json_path_from_repo_or_default,
)
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.git_repo_service.default_implementation import RemoteReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import RemoteWritableGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.local_sync_service.data_types import ExpectedSyncStartupError
from sculptor.services.local_sync_service.data_types import OtherSyncTransitionInProgressError
from sculptor.services.task_service.errors import InvalidTaskOperation
from sculptor.services.task_service.errors import TaskNotFound
from sculptor.startup_checks import check_docker_installed
from sculptor.startup_checks import check_docker_running
from sculptor.startup_checks import check_git_installed
from sculptor.startup_checks import check_is_mutagen_installed
from sculptor.startup_checks import check_is_user_email_field_valid
from sculptor.startup_checks import is_valid_anthropic_api_key
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.errors import is_irrecoverable_exception
from sculptor.utils.secret import Secret
from sculptor.web.auth import AUTHENTIK_SCOPE
from sculptor.web.auth import AppSecretMiddleware
from sculptor.web.auth import PKCE_STORE
from sculptor.web.auth import UserSession
from sculptor.web.auth import generate_pkce_verifier_challenge_and_state
from sculptor.web.auth import get_authorization_url
from sculptor.web.auth import get_logout_url
from sculptor.web.auth import get_redirect_url
from sculptor.web.auth import get_token_url
from sculptor.web.data_types import ArchiveTaskRequest
from sculptor.web.data_types import ArtifactDataResponse
from sculptor.web.data_types import ConfigStatusResponse
from sculptor.web.data_types import CreateInitialCommitRequest
from sculptor.web.data_types import DefaultSystemPromptRequest
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import DiffArtifact
from sculptor.web.data_types import EmailConfigRequest
from sculptor.web.data_types import FeedbackRequest
from sculptor.web.data_types import FixTaskRequest
from sculptor.web.data_types import ForkTaskRequest
from sculptor.web.data_types import GitCommitAndPushRequest
from sculptor.web.data_types import InitializeGitRepoRequest
from sculptor.web.data_types import LogsArtifact
from sculptor.web.data_types import MessageRequest
from sculptor.web.data_types import PrivacyConfigRequest
from sculptor.web.data_types import ProjectInitializationRequest
from sculptor.web.data_types import ProviderStatusInfo
from sculptor.web.data_types import ReadFileRequest
from sculptor.web.data_types import RepoInfo
from sculptor.web.data_types import SendCommandRequest
from sculptor.web.data_types import SendMessageRequest
from sculptor.web.data_types import StartTaskRequest
from sculptor.web.data_types import SuggestionsArtifact
from sculptor.web.data_types import TodoListArtifact
from sculptor.web.data_types import TransferFromLocalToTaskRequest
from sculptor.web.data_types import TransferFromLocalToTaskResponse
from sculptor.web.data_types import TransferFromTaskToLocalRequest
from sculptor.web.data_types import TransferFromTaskToLocalResponse
from sculptor.web.data_types import TransferRepoDecision
from sculptor.web.data_types import TransferRepoDecisionOption
from sculptor.web.data_types import UpdateUserConfigRequest
from sculptor.web.data_types import UserInfo
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import GlobalLocalSyncInfo
from sculptor.web.derived import LocalSyncState
from sculptor.web.derived import LocalSyncStatus
from sculptor.web.derived import SyncedTaskView
from sculptor.web.derived import TaskInterface
from sculptor.web.derived import TaskListUpdate
from sculptor.web.derived import TaskUpdate
from sculptor.web.derived import TaskViewTypes
from sculptor.web.derived import UserUpdate
from sculptor.web.gateway import router as gateway_router
from sculptor.web.merge_actions import merge_into_agent
from sculptor.web.middleware import App
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import get_user_session
from sculptor.web.middleware import get_user_session_for_websocket
from sculptor.web.middleware import lifespan
from sculptor.web.middleware import run_sync_function_with_debugging_support_if_enabled
from sculptor.web.middleware import services_factory
from sculptor.web.middleware import shutdown_event
from sculptor.web.streams import ServerStopped
from sculptor.web.streams import create_initial_task_view
from sculptor.web.streams import stream_task
from sculptor.web.streams import stream_tasks
from sculptor.web.streams import stream_user_updates

T = TypeVar("T")


def validate_project_id(project_id: str) -> ProjectID:
    """Validate and return a ProjectID, raising HTTPException if invalid."""
    try:
        return ProjectID(project_id)
    except (typeid.errors.SuffixValidationException, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid project ID format: {project_id}") from e


for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

PLEASE_POST_IN_DISCORD = "please post in https://discord.com/channels/1391837726583820409/1393200867657781278"
IMBUE_TESTING_GITLAB_MIRROR_REPO_URL: str = (
    "https://gitlab.com/generally-intelligent/gitlab-management-test-repos/integration_testing.git"
)


class InterceptHandler(logging.Handler):
    def emit(self, record) -> None:
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

# Add CORS middleware to allow requests from file:// origins and localhost
APP.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",  # Vite dev server
        "http://localhost:5050",  # Backend server
        "http://127.0.0.1:5050",  # Backend server
        "null",  # file:// URLs report origin as "null"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


# FIXME: decide whether we need this middleware or not,
#  and whether we need the below exception handler to properly log exceptions to sentry
# APP.user_middleware = [middleware for middleware in APP.user_middleware if middleware.cls != ServerErrorMiddleware]


@APP.exception_handler(Exception)
async def irrecoverable_exception_handler(request: Request, exception: Exception):
    if is_irrecoverable_exception(exception):
        logger.opt(exception=exception).info(
            "Irrecoverable exception encountered. Terminating the program immediately."
        )
        telemetry.send_exception_to_posthog(exception)
        telemetry.flush_sentry_and_exit_program(
            SCULPTOR_EXIT_CODE_IRRECOVERABLE_ERROR, "Irrecoverable exception encountered (see logs for details)."
        )
    raise


# Add GZip middleware for compression
# pyre-ignore[6]:
# The signature for middleware classes defined by Starlette (_MiddlewareFactory.__call__) is wrong.
APP.add_middleware(GZipMiddleware, minimum_size=1000)

router = DecoratedAPIRouter(decorator=add_logging_context)


# TODO: NOTE: some unit tests rely on this even though it is not used in the app
@router.get("/api/v1/projects/{project_id}/tasks")
def get_tasks(
    project_id: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    shutdown_event: Event = Depends(shutdown_event),
) -> tuple[TaskViewTypes, ...]:
    """Get list of all tasks"""
    validated_project_id = validate_project_id(project_id)
    logger.info("Getting all tasks")

    update = next(
        iter(
            stream_tasks(
                user_session=user_session,
                project_id=validated_project_id,
                shutdown_event=shutdown_event,
                services=services,
            )
        )
    )
    tasks = tuple(update.task_by_task_id.values() if update is not None else ())
    logger.debug("Returning {} tasks", len(tasks))
    return tasks


@router.post("/api/v1/projects/{project_id}/tasks")
def start_task(
    project_id: ProjectID,
    task_request: StartTaskRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> TaskViewTypes:
    """Start a new task with the given prompt"""
    prompt = task_request.prompt
    interface = task_request.interface
    source_branch = task_request.source_branch
    model = task_request.model

    if not prompt:
        logger.error("Start task request without prompt")
        raise HTTPException(status_code=422, detail="Prompt is required")

    try:
        interface = TaskInterface(interface)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid interface: {interface}. Must be 'terminal' or 'api'",
        ) from e

    logger.info("Starting new task with interface {} and prompt: {}...", interface, prompt[:50])

    services = services
    agent_config = ClaudeCodeSDKAgentConfig() if interface == TaskInterface.API else ClaudeCodeTextAgentConfig()
    task_id = TaskID()

    is_git_state_clean = not task_request.is_including_uncommitted_changes

    # little transaction here -- we don't want to span the whole thing bc then it will be slow
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(project_id)
        assert project is not None, f"Project {project_id} not found"

    with services.git_repo_service.open_local_user_git_repo_for_read(user_session.user_reference, project) as repo:
        # if we are including uncommitted changes, we must shuffle them off to the side before we do anything else
        # otherwise, there is a race condition where the user may change their repo before this task starts
        # and thus the task would have unexpected changes (from the perspective of the user)
        if task_request.is_including_uncommitted_changes:
            copy_of_user_repo_path = get_sculptor_folder() / "user_repo_copies" / str(task_id)
            copy_of_user_repo_path.mkdir(parents=True, exist_ok=True)
            repo.export_current_repo_state(copy_of_user_repo_path)

        # if no source branch is provided, use the current branch
        if source_branch is None or source_branch == "" or " " in source_branch:
            # for now, just log this -- we shouldn't ever get here, so let's find out on sentry
            logger.error("Empty source branch, this is unexpected: {}", source_branch)
            # figure out the source from the repo's current branch, mark this as using unclean git state
            try:
                source_branch = repo.get_current_git_branch()
            except GitRepoError:
                source_branch = ""
        # then figure out the current commit
        if is_git_state_clean:
            initial_commit_hash = repo.get_branch_head_commit_hash(source_branch)
        else:
            initial_commit_hash = repo.get_current_commit_hash()
        repo_path = repo.get_repo_path()
    # TODO: This feels duplicated with some stuff in DockerProvider.create_image.
    devcontainer_json_path: Path = get_devcontainer_json_path_from_repo_or_default(repo_path)
    image_config = LocalDevcontainerImageConfig(
        devcontainer_json_path=str(devcontainer_json_path),
    )

    environment_config = LocalDockerEnvironmentConfig()

    # TODO: post-v1 transition, we should probably make this configurable. Will be nice for testing to ensure that things don't run forever
    max_seconds = None

    task = Task(
        object_id=task_id,
        max_seconds=max_seconds,
        organization_reference=user_session.organization_reference,
        user_reference=user_session.user_reference,
        parent_task_id=None,
        project_id=project.object_id,
        input_data=AgentTaskInputsV1(
            agent_config=agent_config,
            image_config=image_config,
            environment_config=environment_config,
            git_hash=initial_commit_hash,
            initial_branch=source_branch,
            is_git_state_clean=is_git_state_clean,
        ),
    )

    with user_session.open_transaction(services) as transaction:
        inserted_task = services.task_service.create_task(task, transaction)
        task_id = inserted_task.object_id

        # send an initial message to the agent
        if project.default_system_prompt is not None:
            update_system_prompt_message = UpdateSystemPromptUserMessage(
                text=project.default_system_prompt,
                message_id=AgentMessageID(),
            )
            services.task_service.create_message(
                message=update_system_prompt_message,
                task_id=task_id,
                transaction=transaction,
            )

        transaction.add_callback(lambda: _send_configuration_callback(task_id, project, services, settings))

        logger.debug("Creating initial messages...")
        messages = []
        input_user_message = ChatInputUserMessage(
            text=prompt,
            message_id=AgentMessageID(),
            model_name=model,
        )
        messages.append(input_user_message)
        services.task_service.create_message(
            message=input_user_message,
            task_id=task_id,
            transaction=transaction,
        )
        telemetry.emit_posthog_event(
            telemetry.PosthogEventModel(
                name=SculptorPosthogEvent.TASK_START_MESSAGE,
                component=ProductComponent.TASK,
                payload=input_user_message,
                task_id=str(task_id),
            )
        )

    task_view = create_initial_task_view(task, settings)
    for message in messages:
        task_view.add_message(message)
    return task_view


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/fix")
def add_fix(
    project_id: ProjectID,
    task_id: TaskID,
    fix_request: FixTaskRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    with user_session.open_transaction(services):
        received_description = fix_request.description

        fix_info = FixRequest(
            description=received_description,
            project_id=project_id,
            task_id=task_id,
            object_id=FixID(),
        )

        posthog_user = telemetry.get_user_posthog_instance()

        if posthog_user and telemetry.is_consent_allowable(ConsentLevel.LLM_LOGS, posthog_user.user_config):
            event = telemetry.PosthogEventModel(
                name=SculptorPosthogEvent.FIX_ISSUE_SELECT,
                component=ProductComponent.FIX,
                action=telemetry.UserAction.CLICKED,
                payload=fix_info,
            )
            telemetry.emit_posthog_event(event)


class ForkTaskResponse(SerializableModel):
    id: TaskID


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/fork")
def fork_task(
    project_id: ProjectID,
    task_id: TaskID,
    fork_request: ForkTaskRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> CodingAgentTaskView:
    prompt = fork_request.prompt
    model = fork_request.model
    logger.info("Forking task {}", fork_request)
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(task_id, transaction)
        assert task is not None, f"Task {task_id} not found"
        assert not task.is_deleted, "Cannot fork a deleted task"
        input_data = task.input_data
        assert isinstance(input_data, AgentTaskInputsV1), "Can only fork agents"
        current_state = task.current_state
        assert isinstance(current_state, AgentTaskStateV1)

        # Get the project for forking environment config
        project = transaction.get_project(task.project_id)
        assert project is not None, "Project must exist"

        # reset the title and branch name
        mutable_task_state = evolver(current_state)
        assign(mutable_task_state.title, lambda: None)
        assign(mutable_task_state.branch_name, lambda: None)

        # Find the last snapshot message before the next user message after the fork point.
        # This ensures we capture subsequent state changes, like from local syncing.
        found_fork_point = False
        snapshot_message = None

        for existing_message in services.task_service.get_saved_messages_for_task(task_id, transaction):
            if existing_message.message_id == fork_request.chat_message_id:
                found_fork_point = True
            elif found_fork_point:
                # After finding the fork point, look for snapshots
                if isinstance(existing_message, AgentSnapshotRunnerMessage):
                    snapshot_message = existing_message
                elif isinstance(existing_message, ChatInputUserMessage):
                    # Stop at the next user message -- we have the last snapshot before it
                    break
        if snapshot_message is None:
            raise HTTPException(status_code=400, detail="No snapshot message found to fork from")

        assign(mutable_task_state.image, lambda: _fork_image(snapshot_message.image))
        assign(mutable_task_state.branch_name, lambda: None)
        assign(mutable_task_state.title, lambda: None)
        updated_task_state = chill(mutable_task_state)

        new_task = Task(
            object_id=TaskID(),
            max_seconds=task.max_seconds,
            organization_reference=task.organization_reference,
            user_reference=task.user_reference,
            parent_task_id=task.object_id,
            project_id=task.project_id,
            input_data=input_data,
            current_state=updated_task_state,
            outcome=TaskState.QUEUED,
        )
        inserted_task = services.task_service.create_task(new_task, transaction)

        # copy all messages from the original task to the new task up to and including the snapshot message
        messages = []
        for existing_message in services.task_service.get_saved_messages_for_task(task_id, transaction):
            messages.append(existing_message)
            services.task_service.create_message(
                task_id=inserted_task.object_id, message=existing_message, transaction=transaction
            )
            if existing_message.message_id == snapshot_message.message_id:
                break

        # finally make a note that, in fact, we forked this task, in both tasks
        fork_message = ForkAgentSystemMessage(
            parent_task_id=task.object_id,
            child_task_id=inserted_task.object_id,
            fork_point_chat_message_id=fork_request.chat_message_id,
        )

        services.task_service.create_message(task_id=task.object_id, message=fork_message, transaction=transaction)
        services.task_service.create_message(
            task_id=inserted_task.object_id,
            message=fork_message,
            transaction=transaction,
        )
        messages.append(fork_message)

        # send the first post-fork message to the agent
        input_user_message = ChatInputUserMessage(
            text=prompt,
            message_id=AgentMessageID(),
            model_name=model,
        )

        messages.append(input_user_message)
        services.task_service.create_message(
            task_id=inserted_task.object_id, message=input_user_message, transaction=transaction
        )

        with logger.contextualize(log_type=USER_FACING_LOG_TYPE, task_id=new_task.object_id):
            logger.info("Forked task {} from {}", inserted_task.object_id, task_id)

        # Create and return the task view
        task_view = create_initial_task_view(inserted_task, settings)
        for message in messages:
            task_view.add_message(message)
        return task_view


def _fork_image(image: ImageTypes) -> ImageTypes:
    match image:
        case LocalDockerImage() as docker_image:
            # Just return the same image
            return docker_image
        case _:
            raise NotImplementedError()


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/restore")
def restore_task(
    project_id: str,
    task_id: TaskID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> None:
    validate_project_id(project_id)  # Validate project_id but don't need the result
    logger.info("Restoring task {}", task_id)
    with user_session.open_transaction(services) as transaction:
        try:
            services.task_service.restore_task(task_id, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Task not found") from e
        except InvalidTaskOperation as e:
            raise HTTPException(status_code=400, detail="Task is not in a failed state - cannot restore") from e
        with logger.contextualize(log_type=USER_FACING_LOG_TYPE, task_id=task_id):
            logger.info("Restored task {}", task_id)


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/read-file")
def get_file(
    project_id: str,
    task_id: str,
    request: ReadFileRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> str:
    """Read a file from the task's local repository"""
    validate_project_id(project_id)  # Validate project_id but don't need the result
    with user_session.open_transaction(services) as transaction:
        logger.info("Reading file for task {}: {}", task_id, request.file_path)
        try:
            validated_task_id = TaskID(task_id)
        except typeid.errors.SuffixValidationException as e:
            raise HTTPException(status_code=422, detail="Invalid task ID format") from e
        task = services.task_service.get_task(validated_task_id, transaction)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        assert isinstance(task.current_state, AgentTaskStateV1)

        if not task.current_state.task_repo_path:
            raise HTTPException(status_code=400, detail="Task repo path not found")

        file_path = request.file_path
        file_path = task.current_state.task_repo_path / file_path

        environment = services.task_service.get_task_environment(TaskID(task_id), transaction)
        if not environment.exists(str(file_path)):
            logger.error("File not found: {}", file_path)
            raise HTTPException(status_code=404, detail="File not found")

        try:
            return environment.read_file(str(file_path))
        except Exception as e:
            logger.error("Failed to read file {}: {}", file_path, e)
            raise HTTPException(status_code=500, detail="Failed to read file") from e


@router.get("/api/v1/projects/{project_id}/tasks/{task_id}/exist")
def get_task_existence(
    project_id: ProjectID,
    task_id: TaskID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> bool:
    """Get if the task exists and it corresponds to the given project"""
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(task_id, transaction)
        if not task:
            return False
        if task.project_id != project_id:
            return False
    return True


@router.delete("/api/v1/projects/{project_id}/tasks/{task_id}")
def delete_task(
    project_id: str,
    task_id: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Delete a task by ID"""
    validate_project_id(project_id)  # Validate project_id but don't need the result

    with user_session.open_transaction(services) as transaction:
        logger.info("Deleting task {}", task_id)
        try:
            validated_task_id = TaskID(task_id)
        except typeid.errors.SuffixValidationException as e:
            raise HTTPException(status_code=422, detail="Invalid task ID format") from e

        if services.local_sync_service.is_task_synced(validated_task_id):
            logger.debug("local_sync: unsyncing synced task {} so we can delete it", task_id)
            services.local_sync_service.unsync_from_task(validated_task_id, transaction=transaction)

        try:
            services.task_service.delete_task(validated_task_id, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Task not found") from e


# TODO: convert everything to explicitly pass a message request
@contextlib.contextmanager
def await_message_response(
    message_id: AgentMessageID,
    task_id: TaskID,
    services: CompleteServiceCollection,
    message_request: MessageRequest | None = None,
    response_container: list[PersistentRequestCompleteAgentMessage | EphemeralRequestCompleteAgentMessage]
    | None = None,
) -> Generator[None, None, None]:
    if message_request is not None and not message_request.is_awaited:
        yield
        return
    start_time = time.monotonic()
    with services.task_service.subscribe_to_task(task_id) as updates_queue:
        yield
        logger.debug("Waiting for response to message {} in task {}", message_id, task_id)
        while True:
            if message_request is not None:
                if time.monotonic() - start_time > message_request.timeout_seconds:
                    raise TimeoutError(f"Timed out waiting for response to message {message_id} in task {task_id}")
            try:
                update = updates_queue.get(timeout=1.0)
            except queue.Empty:
                pass
            else:
                # these are the two possible types of response message
                if isinstance(update, (PersistentRequestCompleteAgentMessage, EphemeralRequestCompleteAgentMessage)):
                    if update.request_id == message_id:
                        if response_container is not None:
                            response_container.append(update)
                        break


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/messages")
def send_message(
    project_id: str,
    task_id: str,
    message_request: SendMessageRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Send a message to the agent via API interface"""
    validate_project_id(project_id)  # Validate project_id but don't need the result
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    message_id = AgentMessageID()
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(validated_task_id, transaction)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        message = message_request.message
        if not message:
            raise HTTPException(status_code=422, detail="Message required")

        logger.info("Sending message {} to task {}: {}", message_id, validated_task_id, message[:100])

        message = ChatInputUserMessage(
            message_id=message_id,
            text=message,
            model_name=message_request.model,
        )
        telemetry.emit_posthog_event(
            telemetry.PosthogEventModel(
                name=SculptorPosthogEvent.TASK_USER_MESSAGE,
                component=ProductComponent.TASK,
                payload=message,
                task_id=str(validated_task_id),
            )
        )

        services.task_service.create_message(
            message=message,
            task_id=validated_task_id,
            transaction=transaction,
        )


# FIXME: it'd be nice to consolidate everything to this... there's really no need for all of these other routes :-P
@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/message")
def send_message_generic(
    project_id: str,
    task_id: str,
    message_request: MessageRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> SerializedException | None:
    """Generically handles sending any message"""
    logger.info("Sending {} to task {} in project {}", type(message_request.message), task_id, project_id)
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException:
        raise HTTPException(status_code=422, detail="Invalid task ID format")
    message_id = message_request.message.message_id
    response_container: list[PersistentRequestCompleteAgentMessage | EphemeralRequestCompleteAgentMessage] = []
    with await_message_response(message_id, validated_task_id, services, message_request, response_container):
        with user_session.open_transaction(services) as transaction:
            task = services.task_service.get_task(validated_task_id, transaction)
            if not task:
                logger.error("Task {} not found", task_id)
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            services.task_service.create_message(
                message=message_request.message,
                task_id=validated_task_id,
                transaction=transaction,
            )
    if message_request.is_awaited:
        response = only(response_container)
        return response.error
    else:
        return None


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/compact")
def compact_task(
    project_id: str,
    task_id: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Compacts task context"""
    logger.info("Compacting task {} in project {}", task_id, project_id)
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    message_id = AgentMessageID()
    with await_message_response(message_id, validated_task_id, services):
        with user_session.open_transaction(services) as transaction:
            task = services.task_service.get_task(validated_task_id, transaction)
            if not task:
                logger.error("Task {} not found", task_id)
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            services.task_service.create_message(
                message=CompactTaskUserMessage(
                    message_id=message_id,
                    text="/compact",
                ),
                task_id=validated_task_id,
                transaction=transaction,
            )
    return None


# FIXME: consolidate back to a single route for all messages
@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/commands")
def send_command(
    project_id: str,
    task_id: str,
    message_request: SendCommandRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Send a message to the agent via API interface"""
    validate_project_id(project_id)  # Validate project_id but don't need the result
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    message_id = AgentMessageID()
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(validated_task_id, transaction)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        message = message_request.message
        if not message:
            raise HTTPException(status_code=422, detail="Message required")

        logger.info("Sending message to task {}: {}", validated_task_id, message[:100])

        user_message = CommandInputUserMessage(
            message_id=message_id,
            text=message,
            is_included_in_context=message_request.is_included_in_context,
        )
        telemetry.emit_posthog_event(
            telemetry.PosthogEventModel(
                name=SculptorPosthogEvent.TASK_USER_COMMAND,
                component=ProductComponent.TASK,
                payload=user_message,
                task_id=str(validated_task_id),
            )
        )

        services.task_service.create_message(
            message=user_message,
            task_id=validated_task_id,
            transaction=transaction,
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


@router.get("/api/v1/provider_statuses")
def get_provider_statuses(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> tuple[ProviderStatusInfo, ...]:
    """Get the current status of all environment providers"""
    provider_statuses = services.environment_service.get_provider_statuses()

    status_list = []
    for provider_tag, status in provider_statuses.items():
        status_info = ProviderStatusInfo(
            provider=provider_tag,
            status=status,
        )
        status_list.append(status_info)

    return tuple(status_list)


# ====================
# Onboarding routes and Helpers
# ====================


def ensure_posthog_user_identified() -> telemetry.TelemetryInfo:
    """Helper to ensure that the current posthog user is identified, and returns the NEW
    Telemetry info.

    This function encapsulates the logic so that it may be adjusted to be called
    at different points of our signup flow as it changes.

    This function WILL NOT LOG any events to PostHog. You need to know what to
    log yourself.
    """
    # Remember that the following may be "signed_in" or "anonymous"
    original_telemetry_info = get_logged_in_or_anonymous_telemetry_info()

    logger.info("Ensuring identification for user {}", original_telemetry_info)

    if not telemetry.is_posthog_identified():
        logger.info("Identification needs to be submitted")
        telemetry.identify_posthog_user(original_telemetry_info.user_config)
        # Re-get it because it may have changed
        logger.info("We just identified {user}", user=get_logged_in_or_anonymous_telemetry_info())
        return get_logged_in_or_anonymous_telemetry_info()

    logger.info("Identification was unchanged")
    return original_telemetry_info


@router.get("/api/v1/config/status")
def get_config_status(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> ConfigStatusResponse:
    """Check if user config exists and what fields are configured"""
    user_config = get_user_config_instance()

    if not user_config:
        return ConfigStatusResponse(
            has_email=False,
            has_api_key=False,
            has_privacy_consent=False,
            has_telemetry_level=False,
        )

    return ConfigStatusResponse(
        has_email=bool(user_config.user_email) and check_is_user_email_field_valid(user_config),
        has_api_key=services.anthropic_credentials_service.get_anthropic_credentials() is not None,
        has_privacy_consent=user_config.is_privacy_policy_consented,
        has_telemetry_level=user_config.is_telemetry_level_set,
    )


@router.post("/api/v1/config/email")
def save_user_email(
    request: EmailConfigRequest, user_session: UserSession = Depends(get_user_session)
) -> telemetry.TelemetryInfo:
    """Save user email during onboarding

    This function will determine the updated TelemetryInfo for the signed in user, and return that to the frontend.
    """
    # Get or create user config (since this is the first step)
    user_config = get_user_config_instance() or get_default_user_config_instance()

    # Try to get git username from system
    try:
        result = run_blocking(command=["git", "config", "--global", "user.name"])
        git_username = result.stdout.strip()
    except ProcessError:
        # Fall back to email prefix
        git_username = str(request.user_email).split("@")[0]

    user_config = model_update(
        user_config,
        {
            "user_email": request.user_email,
            "user_git_username": git_username,
            "user_id": create_user_id(str(request.user_email)),
            "user_full_name": request.full_name,
            "organization_id": create_organization_id(str(request.user_email)),
            # Saving user email counts as consenting to the Policy email
            "is_privacy_policy_consented": True,
        },
    )

    logger.info("Saved your name {}", request.full_name)
    config_path = get_config_path()
    save_config(user_config, config_path)
    set_user_config_instance(user_config)

    # This next few lines look superficially similar to fire_posthog_event. However, this is
    # different because we absolutely MUST ensure_posthog_user_identified here,
    # whereas in fire_posthog_event we might want to remove that very soon.

    identified_telemetry_info = ensure_posthog_user_identified()
    telemetry_data = telemetry.make_telemetry_event_data(identified_telemetry_info)
    # Documenting for the curious that the following event is set up with a trigger in
    # go/posthog to fire a webhook to go/clay.
    telemetry.emit_posthog_event(
        telemetry.PosthogEventModel(
            name=SculptorPosthogEvent.ONBOARDING_EMAIL_CONFIRMATION,
            component=ProductComponent.ONBOARDING,
            payload=telemetry_data,
        )
    )

    # update sentry to use the email provided
    sentry_sdk.set_user({"username": request.user_email})

    return identified_telemetry_info


def fire_posthog_event(event_name: SculptorPosthogEvent, component: ProductComponent) -> None:
    """Helper to fire a posthog event with the given name and component"""
    # TODO: To determine whether we need to ensure here, or if we can trust the
    # flow.
    identified_telemetry_info = ensure_posthog_user_identified()
    telemetry_data = telemetry.make_telemetry_event_data(identified_telemetry_info)
    telemetry.emit_posthog_event(
        telemetry.PosthogEventModel(
            name=event_name,
            component=component,
            payload=telemetry_data,
        )
    )


@router.get("/api/v1/config/dependencies")
def get_dependencies_status(user_session: UserSession = Depends(get_user_session)) -> DependenciesStatus:
    """Check if required dependencies are installed"""
    ds = DependenciesStatus(
        docker_installed=check_docker_installed(),
        docker_running=check_docker_running(),
        mutagen_installed=check_is_mutagen_installed(),
        git_installed=check_git_installed(),
    )

    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_STARTUP_CHECKS, ProductComponent.ONBOARDING)

    if ds.docker_installed:
        fire_posthog_event(SculptorPosthogEvent.ONBOARDING_DOCKER_INSTALLED, ProductComponent.ONBOARDING)

    if ds.docker_running:
        fire_posthog_event(SculptorPosthogEvent.ONBOARDING_DOCKER_STARTED, ProductComponent.ONBOARDING)

    # Mutagen is always installed, so we don't track an event.

    if ds.git_installed:
        fire_posthog_event(SculptorPosthogEvent.ONBOARDING_GIT_INSTALLED, ProductComponent.ONBOARDING)

    return ds


@router.post("/api/v1/config/api-key")
def save_api_key(
    anthropic_api_key: str = Body(...),
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Save API key during onboarding"""
    if not is_valid_anthropic_api_key(anthropic_api_key):
        raise HTTPException(
            status_code=400,
            detail="Invalid Anthropic API key. Must start with 'sk-ant' and contain only ASCII characters.",
        )

    services.anthropic_credentials_service.set_anthropic_credentials(
        AnthropicApiKey(anthropic_api_key=Secret(anthropic_api_key), generated_from_oauth=False)
    )
    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_ANTHROPIC_API_KEY_SET, ProductComponent.ONBOARDING)
    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_ANTHROPIC_AUTHORIZED, ProductComponent.ONBOARDING)


@router.post("/api/v1/config/privacy")
def save_privacy_settings(
    request: PrivacyConfigRequest, user_session: UserSession = Depends(get_user_session)
) -> None:
    """Save privacy and telemetry consent settings"""
    user_config = get_user_config_instance()
    if not user_config:
        raise HTTPException(status_code=400, detail="User config not initialized. Please complete email setup first.")

    if request.telemetry_level not in (2, 3, 4):
        raise HTTPException(status_code=400, detail="Telemetry level must be an integer between 2 and 4")

    user_config = update_user_consent_level(user_config, request.telemetry_level)

    user_config = model_update(
        user_config,
        {
            "is_privacy_policy_consented": True,
            "is_repo_backup_enabled": request.is_repo_backup_enabled,
            "is_telemetry_level_set": True,
        },
    )

    config_path = get_config_path()
    save_config(user_config, config_path)
    set_user_config_instance(user_config)


@router.post("/api/v1/config/complete")
def complete_onboarding(user_session: UserSession = Depends(get_user_session)) -> None:
    """Complete onboarding by saving config to disk and initializing services"""
    user_config = get_user_config_instance()
    if not user_config:
        raise HTTPException(status_code=400, detail="User config not initialized")
    if not check_is_user_email_field_valid(user_config):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if not user_config.is_privacy_policy_consented:
        raise HTTPException(status_code=400, detail="Privacy policy not consented")

    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_USER_CONFIG_SETTINGS, ProductComponent.ONBOARDING)
    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_COMPLETED, ProductComponent.ONBOARDING)
    fire_posthog_event(SculptorPosthogEvent.USER_CONFIG_SETTINGS_EDITED, ProductComponent.CONFIGURATION)

    logger.info("Onboarding completed successfully")


@router.get("/api/v1/config")
def get_user_config(user_session: UserSession = Depends(get_user_session)) -> UserConfig | None:
    """Get the current user config"""
    return get_user_config_instance()


@router.put("/api/v1/config")
def update_user_config(
    request: UpdateUserConfigRequest, user_session: UserSession = Depends(get_user_session)
) -> UserConfig:
    """Update user config"""
    config_path = get_config_path()
    save_config(request.user_config, config_path)
    set_user_config_instance(request.user_config)
    return request.user_config


@router.post("/api/v1/start_anthropic_oauth")
def start_anthropic_oauth(
    account_type: AnthropicAccountType,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> str:
    services.anthropic_credentials_service.remove_anthropic_credentials()
    _, url = start_anthropic_oauth_impl(services.anthropic_credentials_service, account_type)

    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_ANTHROPIC_OAUTH_STARTED, ProductComponent.ONBOARDING)
    return url


@router.post("/api/v1/cancel_anthropic_oauth")
def cancel_anthropic_oauth(user_session: UserSession = Depends(get_user_session)) -> None:
    cancel_anthropic_oauth_impl()
    fire_posthog_event(SculptorPosthogEvent.ONBOARDING_ANTHROPIC_OAUTH_CANCELLED, ProductComponent.ONBOARDING)


@router.get("/api/v1/anthropic_credentials_exists")
def anthropic_credentials_exists(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> bool:
    do_credentials_exist = services.anthropic_credentials_service.get_anthropic_credentials() is not None
    if do_credentials_exist:
        fire_posthog_event(SculptorPosthogEvent.ONBOARDING_ANTHROPIC_CREDENTIALS_EXIST, ProductComponent.ONBOARDING)
        fire_posthog_event(SculptorPosthogEvent.ONBOARDING_ANTHROPIC_AUTHORIZED, ProductComponent.ONBOARDING)
    return do_credentials_exist


@router.put("/api/v1/projects/{project_id}/default_system_prompt")
def update_default_system_prompt(
    project_id: str,
    default_system_prompt_request: DefaultSystemPromptRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> str | None:
    """Update the default system prompt"""
    default_system_prompt = default_system_prompt_request.default_system_prompt
    if default_system_prompt is None:
        raise HTTPException(status_code=422, detail="default_system_prompt field required")

    logger.info("Updating default system prompt")
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(ProjectID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        updated_project = transaction.upsert_project(
            project.evolve(project.ref().default_system_prompt, default_system_prompt)
        )

    return updated_project.default_system_prompt


@router.patch("/api/v1/projects/{project_id}/tasks/{task_id}/archive")
def archive_task(
    project_id: str,
    task_id: str,
    archive_request: ArchiveTaskRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> bool:
    """Archive or unarchive a task"""
    with user_session.open_transaction(services) as transaction:
        try:
            validated_task_id = TaskID(task_id)
        except typeid.errors.SuffixValidationException as e:
            raise HTTPException(status_code=422, detail="Invalid task ID format") from e

        is_archived = archive_request.is_archived
        if is_archived is None:
            raise HTTPException(status_code=422, detail="is_archived field required")

        if is_archived and services.local_sync_service.is_task_synced(validated_task_id):
            logger.debug("local_sync: unsyncing synced task {} so we can archive it", task_id)
            services.local_sync_service.unsync_from_task(validated_task_id, transaction=transaction)

        try:
            updated_task = services.task_service.set_archived(validated_task_id, is_archived, transaction)
        except TaskNotFound as e:
            raise HTTPException(status_code=404, detail="Task not found") from e

    return is_archived


@router.get("/api/v1/projects/{project_id}/files_and_folders")
def get_files_and_folders(
    project_id: str,
    query: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> list[str]:
    """Get files in the project"""
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(ProjectID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.organization_reference != user_session.organization_reference:
            raise HTTPException(status_code=403, detail="You do not have access to this project")
    try:
        with services.git_repo_service.open_local_user_git_repo_for_read(user_session.user_reference, project) as repo:
            files = repo.list_matching_files(pattern=query)
            folders = repo.list_matching_folders(pattern=query)
            return folders + files

    except subprocess.CalledProcessError as e:
        logger.error("Failed to getting files and folders: {}", e)
        raise HTTPException(status_code=500, detail="Failed to get repository information")
    except Exception as e:
        logger.error("Unexpected error getting files and folders: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


# TODO: post-V1 transition, this should transition to CRUD on Projects (which should know this data)
@router.get("/api/v1/projects/{project_id}/repo_info")
def get_repo_info(
    project_id: ProjectID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> RepoInfo:
    """Get repository information including path and recent branches"""

    try:
        with user_session.open_transaction(services) as transaction:
            project = transaction.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")

        with services.git_repo_service.open_local_user_git_repo_for_read(user_session.user_reference, project) as repo:
            repo_path = repo.get_repo_path()
            try:
                branches = repo.get_recent_branches()
                current_branch = repo.get_current_git_branch()
                num_uncommitted_changes = repo.get_num_uncommitted_changes()
            except FileNotFoundError as e:
                raise HTTPException(status_code=500, detail=f"Could not find repository: {e}") from e

        if not branches:
            raise HTTPException(status_code=500, detail=f"Could not find any branches in repository {repo_path}")

        logger.info(
            "repoPath: {}, currentBranch: {}, recentBranches: {}, projectId: {}, numUncommittedChanges: {}",
            repo_path,
            current_branch,
            branches,
            project.object_id,
            num_uncommitted_changes,
        )

        return RepoInfo(
            repo_path=repo_path,
            current_branch=current_branch,
            recent_branches=branches,
            project_id=project.object_id,
            num_uncommitted_changes=num_uncommitted_changes,
        )
    except HTTPException:
        raise
    except subprocess.CalledProcessError as e:
        log_exception(e, "Failed to get repo info", priority=ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=500, detail="Failed to get repository information")
    except Exception as e:
        log_exception(e, "Unexpected error getting repo info", priority=ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=500, detail=str(e))


@APP.websocket("/api/v1/projects/{project_id}/notifications/stream/ws")
async def stream_notifications_websocket(
    websocket: WebSocket,
    project_id: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session_for_websocket),
    shutdown_event: Event = Depends(shutdown_event),
) -> None:
    validated_project_id = validate_project_id(project_id)
    await to_websocket_stream(
        user_session,
        stream_user_updates(
            user_session=user_session,
            project_id=validated_project_id,
            shutdown_event=shutdown_event,
            services=services,
        ),
        websocket,
    )


@APP.websocket("/api/v1/projects/{project_id}/tasks/stream/ws")
async def stream_tasks_websocket(
    websocket: WebSocket,
    project_id: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session_for_websocket),
    shutdown_event: Event = Depends(shutdown_event),
) -> None:
    """Stream all tasks via Server-Sent Events"""
    validated_project_id = validate_project_id(project_id)
    await to_websocket_stream(
        user_session,
        stream_tasks(
            user_session=user_session,
            project_id=validated_project_id,
            shutdown_event=shutdown_event,
            services=services,
        ),
        websocket,
    )


@APP.websocket("/api/v1/projects/{project_id}/tasks/{task_id}/stream/ws")
async def stream_messages_websocket(
    websocket: WebSocket,
    project_id: ProjectID,
    task_id: TaskID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session_for_websocket),
    shutdown_event: Event = Depends(shutdown_event),
) -> None:
    """Stream current message history via Server-Sent Events"""
    try:
        with user_session.open_transaction(services) as transaction:
            project = transaction.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            if project.organization_reference != user_session.organization_reference:
                raise HTTPException(status_code=403, detail="Cannot stream project which is not in your organization")
            task = services.task_service.get_task(task_id, transaction)
        if task is None or task.project_id != project.object_id:
            raise HTTPException(status_code=403, detail="Cannot stream task which is not in the current project")
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e

    await to_websocket_stream(
        user_session, stream_task(str(task_id), user_session, shutdown_event, services), websocket
    )


async def _try_to_gracefully_close_on_error(websocket: WebSocket, error: BaseException) -> None:
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
    generator: Generator[T | None, None, None],
    websocket: WebSocket,
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
            await _try_to_gracefully_close_on_error(websocket, e)
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
            await websocket.send_json(to_yield)
            # sigh, asyncio is strictly the worst thing in existence
            await asyncio.sleep(0.00001)
    except ServerStopped:
        with logger.contextualize(**user_session.logger_kwargs):
            logger.debug("Server is stopping, closing update stream.")
            await websocket.close(code=1001, reason="Server is stopping")
            return
    except StopIteration:
        with logger.contextualize(**user_session.logger_kwargs):
            logger.debug("Stream ended normally.")
            await websocket.close(code=1000, reason="Stream ended normally")
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


def _get_next_elem(itr) -> str:
    entry = next(itr)
    if entry is None:
        logger.trace("Sending keepalive event")
        to_yield = ": keepalive\n\n"
    else:
        logger.trace("Sending event {}", type(entry))
        to_yield = f"data: {model_dump_json(entry, is_camel_case=True)}\n\n"
    return to_yield


def _get_next_elem_for_websocket(itr, user_session: UserSession) -> str:
    with logger.contextualize(**user_session.logger_kwargs):
        entry = next(itr)
        if entry is None:
            logger.trace("Sending keepalive event")
            to_yield = "null"
        else:
            logger.trace("Sending event {}", type(entry))
            to_yield = entry.model_dump(mode="json", by_alias=True)
        return to_yield


@router.get("/api/v1/projects/{project_id}/tasks/{task_id}/artifacts/{artifact_name}")
def get_artifact_data(
    project_id: str,
    task_id: str,
    artifact_name: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> ArtifactDataResponse:
    try:
        validated_task_id = TaskID(task_id)
    except (typeid.errors.SuffixValidationException, TypeIDPrefixMismatchError) as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e

    return _get_typed_artifact_data(artifact_name, services, task_id, user_session)


@router.get("/api/v1/projects/{project_id}/tasks/{task_id}/artifacts/{artifact_name}/raw")
def get_artifact_data_raw(
    project_id: str,
    task_id: str,
    artifact_name: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> str:
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    artifact_data = _get_artifact_data(artifact_name, services, task_id, user_session)
    return artifact_data


def _get_artifact_data(
    artifact_name: str,
    services: CompleteServiceCollection,
    task_id_str: str,
    user_session: UserSession,
) -> str:
    try:
        task_id = TaskID(task_id_str)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    with user_session.open_transaction(services) as transaction:
        task = services.task_service.get_task(task_id, transaction)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    artifact_data_url = services.task_service.get_artifact_file_url(task_id, artifact_name)
    assert str(artifact_data_url).startswith("file://"), "Only local file artifacts are supported"
    artifact_data_path = Path(str(artifact_data_url).replace("file://", ""))
    if not artifact_data_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact_data = artifact_data_path.read_text(encoding="utf-8")
    logger.debug("Returning artifact at path {}", artifact_data_path)
    logger.trace("returning {} at {}", artifact_data, artifact_data_path)
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
        artifact_type = ArtifactType(artifact_name)
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

        if parsed_json["object_type"] == "SuggestionsArtifact":
            return SuggestionsArtifact.model_validate(parsed_json)
        elif parsed_json["object_type"] == "TodoListArtifact":
            return TodoListArtifact.model_validate(parsed_json)
        elif parsed_json["object_type"] == "LogsArtifact":
            return LogsArtifact.model_validate(parsed_json)
        elif parsed_json["object_type"] == "DiffArtifact":
            return DiffArtifact.model_validate(parsed_json)
        elif parsed_json["object_type"] == "UsageArtifact":
            return UsageArtifact.model_validate(parsed_json)
        else:
            logger.error("Unknown object_type: {}", parsed_json["object_type"])
            raise HTTPException(
                status_code=500,
                detail=f"Unknown artifact object_type: {parsed_json['object_type']}",
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
        raise HTTPException(status_code=422, detail="Invalid artifact data") from e


def _raise_http_exception_if_task_is_not_ready_to_sync(task_id: TaskID, task: Task | None) -> None:
    """Check if a task is ready to be synced."""
    not_ready_please_hold = (
        f"not ready to sync - wait a bit and try again. If this error persists, {PLEASE_POST_IN_DISCORD}"
    )
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found in DB! URL may be incorrect or a system-wide issue occurred.",
        )
    state = task.current_state
    if state is None:
        # TODO it should be trivial to get a task title
        raise HTTPException(status_code=405, detail=f"Task '{task_id}' {not_ready_please_hold}")
    # TODO We should probably be using generics
    assert isinstance(state, AgentTaskStateV1), f"Impossible: Task {task_id} is not an AgentTaskStateV1."
    if state.task_repo_path is None:
        # TODO it should be trivial to get a task title
        raise HTTPException(
            status_code=405,
            detail=f"Task '{state.title or task_id}' {not_ready_please_hold}",
        )


@router.post("/api/sync/projects/{project_id}/tasks/{task_id}/enable")
def enable_task_sync(
    project_id: str,
    task_id: TaskID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Enable sync for a task (only one task can be synced at a time)"""
    if services.local_sync_service.is_task_synced(task_id):
        raise HTTPException(status_code=409, detail=f"Task '{task_id}' is already synced")
    try:
        # TODO: Consider removing special desync path from sync_to_task
        # and instead just calling unsync_from_task and then sync_to_task as two separate / atomic operations
        with services.data_model_service.open_transaction(user_session.request_id) as transaction:
            task = services.task_service.get_task(task_id, transaction)
            _raise_http_exception_if_task_is_not_ready_to_sync(task_id, task)
            services.local_sync_service.sync_to_task(task_id=task_id, transaction=transaction)
    except ExpectedSyncStartupError as e:
        logger.trace("Invalid state to start local syncing from for task {}: {}", task_id, e)
        # hmm... there is a blockers enum in this error now but IDK how to surface that to the frontend.
        # I'm thinking it could be used to pulse the Merge/Push button or something
        raise HTTPException(status_code=409, detail=e.message) from e
    except OtherSyncTransitionInProgressError as e:
        logger.trace("Blocking task {} from local syncing: {}", task_id, e)
        raise HTTPException(status_code=409, detail=str(e)) from e
    except HTTPException as e:
        logger.trace("Blocking unready task {} from local syncing: {}", task_id, e)
        raise e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to enable sync for task {}: {}", task_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/sync/projects/{project_id}/tasks/{task_id}/disable")
def disable_task_sync(
    project_id: str,
    task_id: TaskID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Disable sync for a task"""
    try:
        with services.data_model_service.open_transaction(user_session.request_id) as transaction:
            services.local_sync_service.unsync_from_task(task_id, transaction=transaction)
    except OtherSyncTransitionInProgressError as e:
        logger.trace("Blocking task {} from unsyncing: {}", task_id, e)
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to disable sync for task {}: {} ({})", task_id, e, type(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/sync/global_singleton_state")
def get_global_sync_state_stopgap(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> GlobalLocalSyncInfo | None:
    """Get the current global sync state information"""
    try:
        # Get the current sync session state from the service
        session_state = services.local_sync_service.get_session_state()
        if session_state is None:
            return None

        sync_info = session_state.info
        with services.data_model_service.open_transaction(user_session.request_id) as transaction:
            # Get the task to retrieve title
            task = services.task_service.get_task(sync_info.task_id, transaction)
            if task is None or not isinstance(task.current_state, AgentTaskStateV1):
                return None

            # Get the project to retrieve project path
            project = transaction.get_project(sync_info.project_id)
        if project is None or not project.user_git_repo_url:
            # Don't want to deal with repo missing or soemthing RN
            return None

        project_path = project.user_git_repo_url.replace("file://", "")

        # Convert session state to LocalSyncState
        sync_status = LocalSyncStatus.INACTIVE
        if session_state.high_level_status.value == "ACTIVE":
            sync_status = LocalSyncStatus.ACTIVE
        elif session_state.high_level_status.value == "PAUSED":
            sync_status = LocalSyncStatus.PAUSED

        local_sync_state = LocalSyncState(
            status=sync_status,
            last_updated=session_state.start_time,
            notices=session_state.notices,
        )

        return GlobalLocalSyncInfo(
            synced_task=SyncedTaskView.build(
                task=task,
                sync=local_sync_state,
                sync_started_at=session_state.start_time,
            ),
            project_path=project_path,
        )
    except Exception as e:
        # Could be quite spammy if there's a real issue
        log_exception(e, "Failed to get global sync state", ExceptionPriority.LOW_PRIORITY)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/interrupt")
def interrupt_task(
    project_id: str,
    task_id: str,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Interrupts a given task while it is thinking."""
    logger.info("Getting task {}", task_id)
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    message_id = AgentMessageID()
    with await_message_response(message_id, validated_task_id, services):
        with user_session.open_transaction(services) as transaction:
            task = services.task_service.get_task(validated_task_id, transaction)
            if not task:
                logger.error("Task {} not found", task_id)
                raise HTTPException(status_code=404, detail="Task not found")
            services.task_service.create_message(
                message=InterruptProcessUserMessage(message_id=message_id),
                task_id=validated_task_id,
                transaction=transaction,
            )


def _validate_transfer_repo_parameters(
    project_id: str,
    task_id: str,
    services: CompleteServiceCollection,
    user_session: UserSession,
) -> tuple[Project, Task, Environment]:
    try:
        validated_task_id = TaskID(task_id)
        validated_project_id = ProjectID(project_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task identifiers format") from e

    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(validated_project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        task = services.task_service.get_task(task_id=validated_task_id, transaction=transaction)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if not isinstance(task.current_state, AgentTaskStateV1):
            raise HTTPException(
                status_code=400,
                detail=f"Task {task_id} is not an AgentTask.",
            )

        task_environment = services.task_service.get_task_environment(task_id=task.object_id, transaction=transaction)
        if task_environment is None:
            raise HTTPException(
                status_code=500,
                detail=f"Task {task_id} does not have an active environment",
            )

    task_repo_path = task.current_state.task_repo_path
    if task_repo_path is None:
        raise HTTPException(
            status_code=500,
            detail=f"Task {task_id} does not have a task repository path set.",
        )

    task_repo = RemoteReadOnlyGitRepo(environment=task_environment)
    task_local_branch = task_repo.get_current_git_branch()
    if task_local_branch != task.current_state.branch_name:
        # TODO: is this just a warning for the user, with a request for the agent to change the branch?
        raise HTTPException(
            status_code=409,
            detail=f"Agent is on branch '{task_local_branch}' which doesn't match expected '{task.current_state.branch_name}'.",
        )

    # This is a 409 as we expect the frontend action to be blocked on such a state, even if it's allowed right now.
    task_repo_status = task_repo.get_current_status()
    if task_repo_status.is_in_intermediate_state:
        raise HTTPException(
            status_code=409,
            detail=f"Agent repository is in an inconsistent state: {task_repo_status.describe()}. Have the agent resolve it before synchronizing.",
        )

    return project, task, task_environment


# FIXME: this is work in progress and will be cleaned up with PROD-1905
@APP.post("/api/v1/projects/{project_id}/tasks/{task_id}/transfer-to-agent", operation_id="transferToAgent")
def transfer_from_local_to_task(
    project_id: str,
    task_id: str,
    request: TransferFromLocalToTaskRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> TransferFromLocalToTaskResponse:
    project, task, task_environment = _validate_transfer_repo_parameters(project_id, task_id, services, user_session)

    logger.debug("Request to merge local branch into that of the agent, request: {}", request)

    task_repo = RemoteWritableGitRepo(environment=task_environment)

    with services.git_repo_service.open_local_user_git_repo_for_read(
        user_reference=user_session.user_reference,
        project=project,
    ) as local_repo:
        assert isinstance(local_repo, LocalReadOnlyGitRepo)

        merge_action_result = merge_into_agent(task_repo, local_repo, request.target_local_branch)

    with user_session.open_transaction(services) as transaction:
        # TODO: IMO(mjr) the definition of success here is odd.
        # We kinda have have {USER_ACTION_REJECTED, SUCCESS_WITH_FOLLOWUP_REQUIRED, SUCCESS_CLEAN_AND_SIMPLE}
        message = ManualSyncMergeIntoAgentAttemptedMessage(
            is_attempt_unambiguously_successful=merge_action_result.success,
            is_merge_in_progress=task_repo.is_merge_in_progress,
            labels=[n.label for n in merge_action_result.notices],
        )
        services.task_service.create_message(
            message=message,
            task_id=task.object_id,
            transaction=transaction,
        )
        telemetry.emit_posthog_event(
            telemetry.PosthogEventModel(
                name=SculptorPosthogEvent.MANUAL_SYNC_MERGE_INTO_AGENT_ATTEMPTED,
                component=ProductComponent.MANUAL_SYNC,
                payload=message,
                task_id=str(task_id),
            )
        )

        return TransferFromLocalToTaskResponse(
            success=merge_action_result.success,
            notices=[notice.message for notice in merge_action_result.notices],
            missing_decisions=None,
        )


# FIXME: this is work in progress and will be cleaned up with PROD-1905
# TODO: strikes me as odd that we have the decision flow here and not in the merge-into-agent flow above
@APP.post("/api/v1/projects/{project_id}/tasks/{task_id}/transfer-to-local", operation_id="transferToLocal")
def transfer_from_task_to_local(
    project_id: str,
    task_id: str,
    request: TransferFromTaskToLocalRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> TransferFromTaskToLocalResponse:
    project, task, task_environment = _validate_transfer_repo_parameters(project_id, task_id, services, user_session)
    task_repo = RemoteReadOnlyGitRepo(environment=task_environment)
    response = _transfer_from_task_to_local(
        git_repo_service=services.git_repo_service,
        user_reference=user_session.user_reference,
        project=project,
        task_repo=task_repo,
        request=request,
    )

    message_only_for_posthog = ManualSyncMergeIntoUserAttemptedMessage(
        reached_operation_label=response.reached_operation_or_failure_label if response.success else None,
        reached_operation_failure_label=None if response.success else response.reached_operation_or_failure_label,
        reached_decision_label=response.missing_decisions[0].id if response.missing_decisions else None,
        selection_by_decision_label=request.user_choice_by_decision_id,
    )
    telemetry.emit_posthog_event(
        telemetry.PosthogEventModel(
            name=SculptorPosthogEvent.MANUAL_SYNC_MERGE_INTO_USER_ATTEMPTED,
            component=ProductComponent.MANUAL_SYNC,
            payload=message_only_for_posthog,
            task_id=str(task_id),
        )
    )
    return response


def _transfer_from_task_to_local(
    git_repo_service: GitRepoService,
    user_reference: UserReference,
    project: Project,
    task_repo: RemoteReadOnlyGitRepo,
    request: TransferFromTaskToLocalRequest,
) -> TransferFromTaskToLocalResponse:
    # FIXME: should we explicitly guard against concurrent operations or rely
    #        on the user repo lock below?
    logger.debug("Request to sync local repository to that of the agent, request: {}", request)

    notices: list[str] = []

    task_local_branch = task_repo.get_current_git_branch()

    task_repo_status = task_repo.get_current_status()
    if not task_repo_status.is_clean_and_safe_to_operate_on:
        # TODO(PROD-1893): switch this dialog to an input flag without ability to resolve with a dialog
        logger.trace("Uncommitted changes in task repo: {}", task_repo_status.describe())
        merge_option = "Merge anyway"
        decision_needed = TransferRepoDecision(
            id="TASK_HAS_UNCOMMITTED_CHANGES",
            title="Agent branch has uncommitted work",
            message=f"The agent branch `{task_local_branch}` has changes that aren't committed yet.\n\nYou can go ahead and merge anyway, or cancel to have the agent commit first.",
            detailed_context=task_repo_status.describe(),
            options=(TransferRepoDecisionOption(option=merge_option, is_default=True),),
        )
        option_selected = decision_needed.resolve_user_choice(request.user_choices)
        if option_selected is None:
            return TransferFromTaskToLocalResponse(
                success=False,
                notices=[
                    *notices,
                    "Agent repository has uncommitted changes. Confirmation to ignore them needed.",
                ],
                missing_decisions=[decision_needed],
            )
        if option_selected != merge_option:
            raise HTTPException(
                status_code=400,
                detail=f"Agent repository has uncommitted changes, user's choice is not understood: {option_selected}.",
            )
        notices.append("Ignoring uncommitted changes in Agent's repository")

    with git_repo_service.open_local_user_git_repo_for_write(
        user_reference=user_reference,
        project=project,
    ) as local_repo:
        assert isinstance(local_repo, LocalWritableGitRepo)

        # validate assumptions, but only if it matters
        local_branch = local_repo.get_current_git_branch()
        is_pull_into_current_branch = local_branch == request.target_local_branch
        is_expecting_pull_into_current_branch = request.assumptions.local_branch == request.target_local_branch
        if is_pull_into_current_branch != is_expecting_pull_into_current_branch:
            flag_to_name = lambda is_pull: "Pull" if is_pull else "Fetch"
            raise HTTPException(
                status_code=409,
                detail=f"The local branch was changed and the {flag_to_name(is_expecting_pull_into_current_branch)} operation would become a {flag_to_name(is_pull_into_current_branch)} instead. Please try again in a few seconds.",
            )

        if is_pull_into_current_branch:
            logger.trace("Local branch is the same as target branch, merging into the working tree")

            local_repo_status = local_repo.get_current_status()
            if local_repo_status.is_in_intermediate_state:
                return TransferFromTaskToLocalResponse(
                    success=False,
                    reached_operation_or_failure_label="MERGE_INTO_INTERMEDIATE_STATE_IMPOSSIBLE",
                    notices=[
                        *notices,
                        f"Merge can only proceed against a clean working tree, repository status: {local_repo_status.describe(is_file_changes_list_included=not local_repo_status.is_in_intermediate_state)}",
                    ],
                    missing_decisions=None,
                )
            if not local_repo_status.files.are_clean_including_untracked:
                notices.append(
                    f"Merging into a repository with uncommitted changes: {local_repo_status.files.description}"
                )

            ff_merge_result = local_repo.pull_from_remote(
                remote=str(task_repo.get_repo_url()),
                remote_branch=task_local_branch,
                is_fast_forward_only=True,
            )
            if ff_merge_result.is_merged:
                if ff_merge_result.was_up_to_date:
                    ff_merge_notice = "Already up to date! No merge needed."
                else:
                    ff_merge_notice = "Agent branch merged successfully into local repository (fast-forwarded)"
                return TransferFromTaskToLocalResponse(
                    success=True,
                    reached_operation_or_failure_label="LOCAL_BRANCH_FAST_FORWARDED",
                    notices=[
                        *notices,
                        ff_merge_notice,
                    ],
                )
            elif ff_merge_result.is_stopped_by_uncommitted_changes:
                return TransferFromTaskToLocalResponse(
                    success=False,
                    reached_operation_or_failure_label="LOCAL_UNCOMMITTED_CHANGES_BLOCK_FF_MERGE",
                    notices=[*notices, "The merge was blocked by uncommitted changes in your local repository."],
                )
            else:
                merge_keep_conflict = "Merge"
                merge_abort_on_conflict = "Merge, but abort on conflict"
                decision_needed = TransferRepoDecision(
                    id="FF_MERGE_NOT_POSSIBLE",
                    title="Confirm merge",
                    message="\n\n".join(
                        [
                            f"Your local branch `{request.target_local_branch}` and the agent branch `{task_local_branch}` have diverged—both have new commits.",
                            "To continue, Sculptor needs to run a git merge, which may create merge conflicts. If you want the agent's help resolving conflicts, first push your local branch into the agent branch.",
                        ]
                    ),
                    options=(
                        TransferRepoDecisionOption(option=merge_keep_conflict),
                        TransferRepoDecisionOption(option=merge_abort_on_conflict),
                    ),
                )
                user_choice = decision_needed.resolve_user_choice(request.user_choices)
                if user_choice is None:
                    return TransferFromTaskToLocalResponse(
                        success=False,
                        notices=[*notices, "Fast forward not possible. User decision needed to continue."],
                        missing_decisions=[decision_needed],
                    )

                if user_choice not in (merge_keep_conflict, merge_abort_on_conflict):
                    raise HTTPException(status_code=400, detail=f"Unexpected response to user decision: {user_choice}")
                should_abort_on_conflict = user_choice == merge_abort_on_conflict

                notices.append(
                    f"Merging Agent changes into the local branch{' (aborting on conflicts)' if should_abort_on_conflict else ''}."
                )
                merge_result = local_repo.pull_from_remote(
                    remote=str(task_repo.get_repo_url()),
                    remote_branch=task_local_branch,
                    is_fast_forward_only=False,
                    should_abort_on_conflict=should_abort_on_conflict,
                )
                if merge_result.is_merged:
                    return TransferFromTaskToLocalResponse(
                        success=True,
                        reached_operation_or_failure_label="LOCAL_BRANCH_UPDATED_VIA_MERGE",
                        notices=[
                            *notices,
                            f"Local repository updated ({merge_result.description}).",
                            merge_result.raw_output,
                        ],
                    )
                else:
                    if local_repo.is_merge_in_progress:
                        # if `merge_result.is_aborted` then we have an expectation mismatch to signal to the user
                        failure_label = "MERGE_CONFLICT"
                        user_alert_title = "Merge conflict"
                        user_alert_message = "Merge created conflicts in your local repo. Resolve them and commit locally to finish—or abort the merge."
                    elif merge_result.is_aborted:
                        failure_label = "MERGE_CONFLICT_AND_ABORTED"
                        user_alert_title = "Merge aborted"
                        user_alert_message = (
                            "Merge aborted due to conflicts, as requested. No changes were applied to your local repo."
                        )
                    elif merge_result.is_stopped_by_uncommitted_changes:
                        # this can only happen in case of a race, the earlier attempted fast-forward merge would have stopped the flow earlier
                        user_alert_title = "Merge not possible"
                        failure_label = "MERGE_STOPPED_BY_UNTRACKED_FILES"
                        user_alert_message = "The merge was blocked by uncommitted changes in your local repository. Commit or remove them and try again"
                    else:
                        failure_label = "MERGE_FAILED_WITHOUT_CONFLICT"
                        user_alert_title = "Merge failed"
                        user_alert_message = "Merge didn't complete, but no conflicts were created."

                    return TransferFromTaskToLocalResponse(
                        success=False,
                        reached_operation_or_failure_label=failure_label,
                        notices=[*notices, user_alert_message],
                        missing_decisions=[
                            TransferRepoDecision(
                                id="MERGE_FAILED_ALERT",
                                title=user_alert_title,
                                message=user_alert_message,
                                options=(),  # user can only cancel
                                detailed_context=merge_result.raw_output,
                            )
                        ],
                    )
        else:
            logger.trace("Syncing to a branch that is not checked out locally")
            # fast-forward or forced reset only available
            try:
                # we could first validate that the merge-base matches the local branch HEAD
                # to verify that fast-forward is possible

                # Attempt to fast-forward the unchecked branch, this should always be safe.
                fast_forward_succeeded = local_repo.maybe_fetch_remote_branch_into_local(
                    local_branch=request.target_local_branch,
                    remote=task_repo.get_repo_url(),
                    remote_branch=task_local_branch,
                    dry_run=False,
                    force=False,
                )
                if fast_forward_succeeded:
                    return TransferFromTaskToLocalResponse(
                        success=True,
                        reached_operation_or_failure_label="LOCAL_BRANCH_FAST_FORWARDED",
                        notices=[*notices, "Local branch fast-forwarded to that of the Agent."],
                    )
                else:
                    forced_fetch_possible = local_repo.maybe_fetch_remote_branch_into_local(
                        local_branch=request.target_local_branch,
                        remote=task_repo.get_repo_url(),
                        remote_branch=task_local_branch,
                        dry_run=True,
                        force=True,
                    )
                    if not forced_fetch_possible:
                        # no idea what's blocking us!
                        return TransferFromTaskToLocalResponse(
                            success=False,
                            reached_operation_or_failure_label="LOCAL_BRANCH_FORCE_FETCH_IMPOSSIBLE",
                            notices=[
                                *notices,
                                # TODO: attach the git log here
                                "Fetching the branch is not possible, even if forced. Try again and contact support if failed.",
                            ],
                        )
                    else:
                        overwrite_option = "Overwrite with agent branch"
                        decision_needed = TransferRepoDecision(
                            id="FORCE_FETCH",
                            title="Replace local branch with agent branch?",
                            message="\n\n".join(
                                [
                                    f"Your local branch `{request.target_local_branch}` has diverged from the agent branch `{task_local_branch}`.",
                                    f"You can choose to **Overwrite**, which will replace your local branch with the agent branch, **and your local changes will be lost**.",
                                    "\n".join(
                                        [
                                            "If you want Sculptor to perform a merge instead, cancel and either:",
                                            f"check out `{request.target_local_branch}` locally and try again, or",
                                            f"push your branch into the agent first then fetch it back.",
                                        ]
                                    ),
                                ]
                            ),
                            # TODO: we can also ask the user to switch to that branch and restart the whole flow with an option of merging things
                            options=(
                                TransferRepoDecisionOption(
                                    option=overwrite_option,
                                    is_destructive=True,
                                ),
                            ),
                        )
                        option_selected = decision_needed.resolve_user_choice(request.user_choices)
                        if option_selected is None:
                            return TransferFromTaskToLocalResponse(
                                success=False,
                                notices=[
                                    *notices,
                                    "Local branch is diverged. User confirmation to overwrite needed.",
                                ],
                                missing_decisions=[decision_needed],
                            )
                        if option_selected != overwrite_option:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Local branch divergent but user's choice is not understood: {option_selected}.",
                            )
                        # TODO: verify that the decision applies to the same operation (before/after local git commits)
                        # TODO: show the actual git output
                        if local_repo.maybe_fetch_remote_branch_into_local(
                            local_branch=request.target_local_branch,
                            remote=task_repo.get_repo_url(),
                            remote_branch=task_local_branch,
                            dry_run=False,
                            force=True,
                        ):
                            return TransferFromTaskToLocalResponse(
                                success=True,
                                reached_operation_or_failure_label="LOCAL_BRANCH_UPDATE_FORCED",
                                notices=[
                                    *notices,
                                    "Local branch updated forcefully to that of the Agent",
                                ],
                            )
                        else:
                            return TransferFromTaskToLocalResponse(
                                success=False,
                                notices=[
                                    *notices,
                                    "Local branch could not be forcefully updated to that of the Agent",
                                ],
                                missing_decisions=None,
                            )

            except GitRepoError as e:
                # we are not expecting any errors from the normal fetch operation
                # one reason could be that repo is dead, another is that there was
                # a race and the user has actually checked out this branch while we
                # were attempting to fetch it
                return TransferFromTaskToLocalResponse(
                    success=False,
                    reached_operation_or_failure_label="UNEXPECTED_GIT_FAILURE",
                    notices=[
                        f"Unexpected error when performing git operation: {str(e)}",
                    ],
                )


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/git-commit")
def git_commit_in_task(
    project_id: str,
    task_id: str,
    request: GitCommitAndPushRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> None:
    """Triggers a git commit and push operation for the given task."""
    logger.info("Git commit and push requested for task {}", task_id)
    try:
        validated_task_id = TaskID(task_id)
    except typeid.errors.SuffixValidationException as e:
        raise HTTPException(status_code=422, detail="Invalid task ID format") from e
    message_id = AgentMessageID()
    with await_message_response(message_id, validated_task_id, services):
        with user_session.open_transaction(services) as transaction:
            task = services.task_service.get_task(validated_task_id, transaction)
            if not task:
                logger.error("Task {} not found", task_id)
                raise HTTPException(status_code=404, detail="Task not found")
            services.task_service.create_message(
                message=GitCommitAndPushUserMessage(
                    message_id=message_id,
                    commit_message=request.commit_message,
                    is_pushing=False,
                ),
                task_id=validated_task_id,
                transaction=transaction,
            )


@router.post("/api/v1/testing/cleanup-images")
def trigger_image_cleanup(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> dict[str, tuple[str, ...]]:
    """
    Manually trigger image cleanup for testing purposes.
    This endpoint is only available in testing mode.

    Returns:
        Dictionary with 'deleted_images' containing tuple of deleted image IDs
    """
    # Only allow this endpoint in testing mode
    if not settings.TESTING.INTEGRATION_ENABLED:
        raise HTTPException(status_code=403, detail="This endpoint is only available in testing mode")

    logger.info("Manual image cleanup triggered by user {}", user_session.user_reference)

    try:
        deleted_images = services.environment_service.remove_stale_images()
        logger.info("Manual cleanup completed. Deleted {} images", len(deleted_images))
        return {"deleted_images": deleted_images}
    except Exception as e:
        logger.error("Error during manual image cleanup: {}", e)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup images: {str(e)}") from e


@router.get("/api/v1/version")
def get_version() -> str:
    return f"V1 — {version.__version__}"


# The /login and /callback endpoints below are used for the OAuth2 flow with Proof of Key Exchange (PKCE) with Authentik.
# Here's a good description of the flow (even if for a different auth provider):
#   - https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow-with-pkce
#
# We could delegate this to a library like Authlib.
# For now, we didn't do it because:
#   - Authlib's fastAPI integration assumes async setup which we don't use.
#     (It can be circumvented by going to lower-level bits of Authlib but then we don't get that much from the library.)
#   - Authlib's licensing is a little unclear.
#   - And there are typing issues related to dynamic attributes in Authlib.
#
# None of these reasons are too strong. But the implementation below isn't too complex so I didn't feel compelled to switch (yet).


class PostHogEventStamp(telemetry.PosthogEventPayload):
    """A simple wrapper for IDs that can be used for joining and grouping events in PostHog."""

    stamp: str = telemetry.without_consent()


def _get_posthog_event_stamp(code_verifier: str) -> PostHogEventStamp:
    """
    Use the already existing code verifier to generate a unique event ID for PostHog.

    code_verifier is sensitive, so we hash it.

    (We hash twice so that the event_id is not the same as the code_challenge. code_challenge is supposed to not be sensitive but still.)

    """
    stamp = hashlib.sha256(hashlib.sha256(code_verifier.encode()).digest()).hexdigest()[:32]
    return PostHogEventStamp(stamp=stamp)


# TODO: let's double-check if it's fine that this endpoint can be called from the null origin.
@APP.get("/api/v1/auth/login", operation_id="login")
def login(next_path: str = "/", settings: SculptorSettings = Depends(get_settings)) -> RedirectResponse:
    state, code_verifier, code_challenge = generate_pkce_verifier_challenge_and_state()
    PKCE_STORE.set(state, code_verifier, next_path)

    params = {
        "response_type": "code",
        "client_id": settings.AUTHENTIK_CLIENT_ID,
        "redirect_uri": get_redirect_url(settings),
        "scope": AUTHENTIK_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorization_url = get_authorization_url(settings)
    telemetry.emit_posthog_event(
        telemetry.PosthogEventModel(
            name=SculptorPosthogEvent.LOGIN_INITIATED,
            component=ProductComponent.AUTH,
            payload=_get_posthog_event_stamp(code_verifier),
        )
    )
    return RedirectResponse(f"{authorization_url}?{urlencode(params)}")


@APP.get("/api/v1/auth/callback", operation_id="authCallback")
async def auth_callback(code: str, state: str, settings: SculptorSettings = Depends(get_settings)) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    code_verifier_and_next_path = PKCE_STORE.get(state)
    if code_verifier_and_next_path is None:
        raise HTTPException(status_code=400, detail="Invalid state or expired login")

    # Exchange code for token using PKCE code_verifier (for public clients).
    code_verifier, next_path = code_verifier_and_next_path
    token_url = get_token_url(settings)
    with httpx.Client() as client:
        token_response = client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.AUTHENTIK_CLIENT_ID,
                "code": code,
                "redirect_uri": get_redirect_url(settings),
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )
        if not token_response.is_success:
            raise HTTPException(
                status_code=token_response.status_code,
                detail="Failed to exchange code for tokens",
            )
        tokens = token_response.json()

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    protocol, domain, port = settings.PROTOCOL, settings.DOMAIN, settings.FRONTEND_PORT
    PKCE_STORE.delete(code_verifier)
    redirect_url = f"{protocol}://{domain}:{port}{next_path}?accessToken={access_token}&refreshToken={refresh_token}"
    telemetry.emit_posthog_event(
        telemetry.PosthogEventModel(
            name=SculptorPosthogEvent.LOGIN_SUCCEEDED,
            component=ProductComponent.AUTH,
            payload=_get_posthog_event_stamp(code_verifier),
        )
    )
    return RedirectResponse(url=redirect_url)


class TokenPair(SerializableModel):
    access_token: str
    refresh_token: str


class RefreshData(SerializableModel):
    refresh_token: str


@APP.post("/api/v1/auth/renew-tokens", operation_id="renewTokens")
async def renew_tokens(refresh_data: RefreshData, settings: SculptorSettings = Depends(get_settings)) -> TokenPair:
    """
    Endpoint to fetch a new access token and a new refresh token using the refresh token stored in a cookie.

    """
    token_url = get_token_url(settings)

    with httpx.Client() as client:
        authentik_response = client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.AUTHENTIK_CLIENT_ID,
                "refresh_token": refresh_data.refresh_token,
            },
            headers={"Accept": "application/json"},
        )
        if not authentik_response.is_success:
            raise HTTPException(
                status_code=authentik_response.status_code,
                detail="Failed to refresh token",
            )
        tokens = authentik_response.json()

    return TokenPair(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])


@APP.get("/api/v1/auth/logout", operation_id="logout")
async def logout(
    settings: SculptorSettings = Depends(get_settings),
    user_session: UserSession = Depends(get_user_session),
) -> RedirectResponse:
    protocol, domain, port = settings.PROTOCOL, settings.DOMAIN, settings.FRONTEND_PORT
    # When done, redirect to the home page.
    next_url = f"{protocol}://{domain}:{port}/"
    logout_url = get_logout_url(settings, next_url)
    response = RedirectResponse(url=logout_url)
    return response


@APP.get("/api/v1/auth/me", operation_id="currentUser")
async def current_user(user_session: UserSession = Depends(get_user_session)) -> UserInfo | None:
    if user_session.is_anonymous:
        return None
    return UserInfo(user_reference=user_session.user_reference, email=user_session.user_email)


@router.delete("/api/v1/projects/{project_id}/tasks/{task_id}/messages/{message_id}")
def delete_message(
    project_id: ProjectID,
    task_id: TaskID,
    message_id: AgentMessageID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Delete a message from the task"""
    new_message_id = AgentMessageID()
    with await_message_response(new_message_id, task_id, services):
        with user_session.open_transaction(services) as transaction:
            services.task_service.create_message(
                message=RemoveQueuedMessageUserMessage(message_id=new_message_id, target_message_id=message_id),
                task_id=task_id,
                transaction=transaction,
            )


class FeedbackRequestPayload(telemetry.PosthogEventPayload):
    """Payload for feedback request. All fields are consented to since user has to explicitly submit feedback."""

    feedback_type: str | None = telemetry.without_consent()
    message_id: str | None = telemetry.without_consent()
    comment: str | None = telemetry.without_consent()
    issue_type: str | None = telemetry.without_consent()
    saved_agent_messages_s3_path: str | None = telemetry.without_consent()


class FeedbackSavedAgentMessagesPayload(SerializableModel):
    """Payload for saved agent messages in feedback request.

    This is not used for PostHog events, but to pack and serialize for s3 storage.
    """

    task_id: TaskID
    messages: list[PersistentMessageTypes]


@router.post("/api/v1/projects/{project_id}/tasks/{task_id}/messages/{message_id}/feedback")
def submit_feedback(
    project_id: str,
    task_id: str,
    message_id: str,
    feedback_request: FeedbackRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Submit feedback for an entire task."""
    validate_project_id(project_id)  # Validate project_id but don't need the result

    try:
        validated_task_id = TaskID(task_id)
    except TypeIDPrefixMismatchError as e:
        raise HTTPException(status_code=422, detail=f"Invalid task ID {e}") from e

    feedback_type = feedback_request.feedback_type
    comment = feedback_request.comment or ""
    issue_type = feedback_request.issue_type or ""

    if feedback_type not in ["positive", "negative"]:
        raise HTTPException(status_code=422, detail="feedback_type must be 'positive' or 'negative'")

    logger.info(
        "Received feedback for task {}: type={} comment='{}' issue_type='{}'",
        validated_task_id,
        feedback_type,
        comment,
        issue_type,
    )

    # Extract all messages for the task to include in the feedback
    # Here we upload to s3 as the payload size could exceed PostHog's 1MB event size limit.
    with user_session.open_transaction(services) as transaction:
        all_messages = services.task_service.get_saved_messages_for_task(validated_task_id, transaction)
        logger.trace("Extracted {} messages for task {}", len(all_messages), validated_task_id)
        for message in all_messages:
            logger.trace(
                "Message ID: {}, Source: {}, Text: {}", message.message_id, message.source, message.model_dump()
            )

        s3_bytes = json.dumps(
            FeedbackSavedAgentMessagesPayload(task_id=validated_task_id, messages=list(all_messages)).model_dump_json()
        ).encode("utf-8")

        # Create a S3 upload for the DB transaction contents
        s3_upload_url = upload_to_s3(SculptorPosthogEvent.TASK_USER_FEEDBACK.value, ".json", s3_bytes)

        # Create a Posthog event with the feedback
        posthog_event = telemetry.PosthogEventModel(
            name=SculptorPosthogEvent.TASK_USER_FEEDBACK,
            component=ProductComponent.TASK,
            payload=FeedbackRequestPayload(
                feedback_type=feedback_type,
                message_id=message_id,
                comment=comment,
                issue_type=issue_type,
                saved_agent_messages_s3_path=s3_upload_url,
            ),
            task_id=str(validated_task_id),
        )
        telemetry.emit_posthog_event(posthog_event)


@router.get("/api/v1/ping_sentry")
def ping_sentry(
    user_session: UserSession = Depends(get_user_session),
) -> None:
    log_exception(
        Exception("This is a test logged exception"),
        message="This is a test logged exception",
    )
    raise Exception("This is a test raised exception")


@router.post("/api/v1/projects/{project_id}/activate")
def activate_project(
    project_id: ProjectID,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
    settings: SculptorSettings = Depends(get_settings),
) -> None:
    with user_session.open_transaction(services) as transaction:
        project = transaction.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.organization_reference != user_session.organization_reference:
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        services.project_service.activate_project(project)

        current_config = services.configuration_broadcast_service.get_current_project_configuration(project.object_id)
        if (
            current_config.gitlab_token
            and current_config.gitlab_url
            and not services.configuration_broadcast_service.is_token_expired(current_config)
        ):
            logger.debug("GitLab token and URL already available for project and not expired, sending configuration")
            services.configuration_broadcast_service.send_configuration_to_project(project.object_id, current_config)
        else:
            logger.info("No valid project-specific GitLab configuration available, attempting to provision")
            if settings.is_imbue_gateway_configured:
                _provision_gitlab_token_for_project(project, services, settings)


def _send_configuration_callback(
    task_id: TaskID,
    project: Project,
    services: CompleteServiceCollection,
    settings: SculptorSettings,
) -> None:
    logger.debug("Rebroadcasting current configuration to new task")
    services.configuration_broadcast_service.rebroadcast_current_configuration_to_task(task_id)

    current_config = services.configuration_broadcast_service.get_current_project_configuration(project.object_id)
    if (
        current_config.gitlab_token
        and current_config.gitlab_url
        and not services.configuration_broadcast_service.is_token_expired(current_config)
    ):
        logger.debug("GitLab token and URL already available for project, sending configuration to new task")
        services.configuration_broadcast_service.send_configuration_to_project(
            project.object_id,
            current_config,
        )
    else:
        logger.debug("No valid project-specific GitLab configuration available, attempting to provision for new task")
        if settings.is_imbue_gateway_configured:
            _provision_gitlab_token_for_project(project, services, settings)


def _provision_gitlab_token_for_project(
    project: Project, services: CompleteServiceCollection, settings: SculptorSettings
) -> None:
    user_config = get_user_config_instance()
    if not user_config or not user_config.is_repo_backup_enabled:
        logger.info("GitLab mirroring disabled or user config not available")
        return

    try:
        if not project.user_git_repo_url or not project.user_git_repo_url.startswith("file://"):
            logger.error("Project does not have a valid local git repository URL")
            return

        project_path = Path(project.user_git_repo_url.replace("file://", ""))
        logger.info("Provisioning GitLab token for project: {}", project_path)

        result = run_blocking(command=["git", "rev-parse", "HEAD"], cwd=project_path, is_output_traced=False)
        base_commit_hash = result.stdout.strip()
        logger.debug("Base commit hash: {}", base_commit_hash)

        settings = services.settings
        gateway_url = urljoin(settings.IMBUE_GATEWAY_BASE_URL, GatewayRemoteAPIEndpoints.GITLAB_ANONYMOUS_PAT_ENDPOINT)
        params = {"base_commit_hash": base_commit_hash, "user_id": user_config.anonymous_access_token}

        logger.debug("Gateway url for PAT is {}", gateway_url)

        access_token = None
        gitlab_project_url = None

        logger.debug("Gitlab mirroring is enabled: {}", settings.is_imbue_gateway_configured)
        if settings.is_imbue_gateway_configured:
            # integration test
            if settings.GITLAB_DEFAULT_TOKEN != "":
                access_token = settings.GITLAB_DEFAULT_TOKEN
                gitlab_project_url = IMBUE_TESTING_GITLAB_MIRROR_REPO_URL
            else:
                try:
                    response = requests.post(gateway_url, params=params, timeout=5)
                    response.raise_for_status()

                    response_data = response.json()
                    access_token = response_data.get("accessToken")
                    gitlab_project_url = response_data.get("url")
                except requests.exceptions.Timeout:
                    logger.error("Call to imbue_gateway reached local timeout, continuing without mirroring.")
        else:
            logger.info("GitLab mirroring disabled, PAT not generated")

        if access_token and gitlab_project_url:
            logger.info("Retrieved GitLab access token from imbue-gateway")
            logger.debug("Gitlab project url: {}", gitlab_project_url)

            expiration_time = (datetime.now() + timedelta(days=30)).isoformat()

            configuration = ProjectConfiguration(
                gitlab_token=access_token, gitlab_url=gitlab_project_url, token_expires_at_iso=expiration_time
            )
            services.configuration_broadcast_service.send_configuration_to_project(project.object_id, configuration)

            logger.debug("Successfully sent GitLab configuration to project: {}", project.object_id)
        else:
            logger.info("Failed to retrieve GitLab access token from imbue-gateway")

    except Exception as e:
        logger.error("Failed to provision GitLab token for project {}: {}", project.object_id, e)


@router.get("/api/v1/projects/active")
def get_active_projects(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> tuple[Project, ...]:
    """Get all currently active projects for the session."""

    return services.project_service.get_active_projects()


@router.post("/api/v1/projects/initialize")
def initialize_project(
    request: ProjectInitializationRequest,
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> Project:
    project_path = Path(request.project_path).expanduser()

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

    # ensure we have an initial commit, and if not, offer to create one
    try:
        run_blocking(command=["git", "rev-parse", "HEAD"], cwd=project_path, is_checked=True)
    except ProcessError:
        raise HTTPException(
            status_code=409,
            detail="Selected git repository has no commits. Please create an initial commit first.",
        )

    with user_session.open_transaction(services) as transaction:
        project = services.project_service.initialize_project(
            project_path=project_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
    return project


@router.get("/api/v1/projects")
def list_projects(
    services: CompleteServiceCollection = Depends(services_factory),
    user_session: UserSession = Depends(get_user_session),
) -> tuple[Project, ...]:
    with user_session.open_transaction(services) as transaction:
        return transaction.get_projects(organization_reference=user_session.organization_reference)


@router.post("/api/v1/projects/init-git")
def initialize_git_repository(
    request: InitializeGitRepoRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    """Initialize a directory as a git repository with an initial commit."""
    project_path = Path(request.project_path).expanduser()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Project path is not a directory: {project_path}")
    if (project_path / ".git").exists():
        raise HTTPException(status_code=400, detail=f"Directory is already a git repository: {project_path}")

    logger.info("Initializing git repository at: {}", project_path)

    try:
        run_blocking(command=["git", "init"], cwd=project_path, is_output_traced=False)
        run_blocking(
            command=["git", "commit", "--allow-empty", "-m", "Initial commit"],
            cwd=project_path,
            is_output_traced=False,
        )
    except ProcessError as e:
        logger.error("Failed to initialize git repository: {}", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to initialize git repository: {e.stderr if e.stderr else str(e)}"
        ) from e


@router.post("/api/v1/projects/create-initial-commit")
def create_initial_commit(
    request: CreateInitialCommitRequest,
    user_session: UserSession = Depends(get_user_session),
) -> None:
    project_path = Path(request.project_path).expanduser()

    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Project path is not a directory: {project_path}")

    logger.info("Creating initial commit in git repository at: {}", project_path)

    try:
        run_blocking(command=["git", "add", "-A"], cwd=project_path, is_output_traced=False)
        run_blocking(
            command=["git", "commit", "--allow-empty", "-m", "Initial commit"],
            cwd=project_path,
            is_output_traced=False,
        )
    except ProcessError as e:
        logger.error("Failed to create initial commit: {}", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to create initial commit: {e.stderr if e.stderr else str(e)}"
        ) from e


# Dummy routes to include WebSocket types in OpenAPI schema
@router.get("/_ws_types/task_update")
def _ws_type_task_update() -> TaskUpdate:
    """Include TaskUpdate in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


@router.get("/_ws_types/task_list_update")
def _ws_type_task_list_update() -> TaskListUpdate:
    """Include TaskListUpdate in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


@router.get("/_ws_types/user_update")
def _ws_type_user_update() -> UserUpdate:
    """Include UserUpdate in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


@router.get("/_types/user_config_field")
def _type_user_config_field() -> UserConfigField:
    """Include UserConfigField enum in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


@router.get("/_element_tags")
def _element_tags() -> ElementIDs:
    """Include UserUpdate in schema"""
    raise HTTPException(status_code=501, detail="This endpoint exists only for OpenAPI schema generation")


APP.include_router(router)
APP.include_router(gateway_router)

APP.add_middleware(AppSecretMiddleware, settings_factory=get_settings)


# TODO (PROD-2161): either we can remove this or leave it for debugging, it might fail depending on what we change with the build process
# To avoid conflicts with the API routes, we write this route last. This route
# must be loaded _after_ APP.include_router, which performs delayed routing.
@APP.get("/{filename:path}")
def serve_static(filename: str = "index.html") -> StreamingResponse:
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


def _load_file(filename: str, static_dir) -> StreamingResponse:
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
        response = StreamingResponse(
            create_file_generator(resolved_final_file_path),
            media_type=mime_type,
            headers={"Content-Length": str(resolved_final_file_path.stat().st_size)},
        )
    return response


def create_file_generator(file_path):
    def file_generator():
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            while chunk:
                yield chunk
                chunk = f.read(8192)

    return file_generator()
