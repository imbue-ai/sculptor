import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Generator
from typing import Mapping
from typing import Sequence
from urllib.parse import urlparse
from urllib.parse import urlunparse

import coolname
from loguru import logger

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import is_running_within_a_pytest_tree
from imbue_core.constants import ExceptionPriority
from imbue_core.git import get_repo_url_from_folder
from imbue_core.itertools import only
from imbue_core.nested_evolver import assign
from imbue_core.nested_evolver import chill
from imbue_core.nested_evolver import evolver
from imbue_core.processes.local_process import RunningProcess
from imbue_core.processes.local_process import run_background
from imbue_core.processes.local_process import run_blocking
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import TELEMETRY_TASK_INFO_JSON_STATE_FILE
from imbue_core.sculptor.telemetry import TelemetryProjectInfo
from imbue_core.sculptor.telemetry import TelemetryTaskInfo
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.serialization import SerializedException
from imbue_core.subprocess_utils import ProcessError
from imbue_core.thread_utils import ObservableThread
from sculptor.agents.claude_code_sdk.agent import INITIAL_GIT_HASH_STATE_FILE
from sculptor.agents.claude_code_sdk.agent import SOURCE_BRANCH_STATE_FILE
from sculptor.agents.claude_code_sdk.agent import TASK_BRANCH_STATE_FILE
from sculptor.config.settings import SculptorSettings
from sculptor.config.telemetry_info import get_telemetry_info
from sculptor.config.user_config import get_user_config_instance
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import DockerEnvironment
from sculptor.interfaces.agents.v1.agent import EnvironmentCreatedRunnerMessage
from sculptor.interfaces.agents.v1.agent import EnvironmentStoppedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ForkAgentSystemMessage
from sculptor.interfaces.agents.v1.agent import WarningRunnerMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.interfaces.environments.v1.base import SSHD_SERVER_NAME
from sculptor.interfaces.environments.v1.constants import ENVIRONMENT_WORKSPACE_DIRECTORY
from sculptor.interfaces.environments.v1.constants import SCULPTOR_USER
from sculptor.interfaces.environments.v1.errors import EnvironmentConfigurationChangedError
from sculptor.interfaces.environments.v1.errors import EnvironmentNotFoundError
from sculptor.primitives.constants import USER_FACING_LOG_TYPE
from sculptor.primitives.ids import UserReference
from sculptor.server.llm_content_generation import generate_title_and_branch_from_initial_prompt
from sculptor.server.llm_content_generation import generate_title_only_from_initial_prompt
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.tasks.handlers.run_agent.git import run_git_command_in_environment
from sculptor.tasks.handlers.run_agent.git import run_git_command_local
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.secret import Secret
from sculptor.utils.timeout import log_runtime
from sculptor.utils.timeout import timeout_monitor


def sanitize_git_url_robust(url: str | None) -> str | None:
    if not isinstance(url, str) or not url:
        return None

    try:
        url = url.strip()

        if url.startswith("file://"):
            return url

        if url.startswith("git@"):
            return _convert_ssh_to_https(url)

        if url.startswith("ssh://"):
            return _convert_ssh_protocol_to_https(url)

        parsed = urlparse(url)
        if parsed.hostname:
            new_netloc = parsed.hostname
            if parsed.port:
                new_netloc += f":{parsed.port}"

            clean_parts = parsed._replace(netloc=new_netloc)
            return str(urlunparse(clean_parts))
    except ValueError:
        return None
    return None


def _convert_ssh_to_https(ssh_url: str) -> str | None:
    if not ssh_url.startswith("git@"):
        return None

    try:
        parts = ssh_url.split("@", 1)
        if len(parts) != 2:
            return None

        host_path = parts[1]
        if ":" in host_path:
            host, path = host_path.split(":", 1)
            if path.endswith(".git"):
                path = path[:-4]
            return f"https://{host}/{path}"

        return None
    except Exception:
        return None


def _convert_ssh_protocol_to_https(ssh_url: str) -> str | None:
    if not ssh_url.startswith("ssh://"):
        return None

    try:
        ssh_url = ssh_url[6:]  # Remove "ssh://"

        if "@" in ssh_url:
            credentials, rest = ssh_url.split("@", 1)
            host_path = rest
        else:
            host_path = ssh_url

        if "/" in host_path:
            host, path = host_path.split("/", 1)
            if path.endswith(".git"):
                path = path[:-4]
            return f"https://{host}/{path}"

        return None
    except Exception:
        return None


# it will take at most this much time to notice when the process has finished
_POLL_SECONDS: float = 1.0
# if it takes longer than this, we give up waiting for the title and branch name to be predicted
_TITLE_NAME_TIMEOUT_SECONDS: float = 10.0
_FIXED_BRANCH_NAME_COUNTER_FOR_TESTING = 0

_ENVIRONMENT_CREATION_TIMEOUT_SECONDS: float = 300.0
_IMAGE_CREATION_TIMEOUT_SECONDS: float = 300.0


def hard_overwrite_full_agent_workspace(
    environment: Environment,
    user_repo_path: Path,
    task_id: TaskID | None = None,
    services: ServiceCollectionForTask | None = None,
    task_id_if_keep_uncommitted: TaskID | None = None,
) -> None:
    # Step 1: Run git status to get ignored files and dirs
    result = run_blocking(
        ["git", "status", "--ignored", "-s", "--untracked-files=normal"],
        cwd=user_repo_path,
    )

    # Step 2: Parse the output and turn it into rsync exclude patterns
    exclude_patterns = []
    for line in result.stdout.splitlines():
        if line.startswith("!! "):
            path = line[3:].strip()
            exclude_patterns.append("/" + path)

    exclude_patterns.append("/.git/hooks")

    # Step 3: write them to a temporary file
    with tempfile.NamedTemporaryFile(mode="w") as f:
        f.write("\n".join(exclude_patterns) + "\n")
        f.flush()

        # Step 4: run rsync with the exclude file
        with log_runtime("rsyncing in-container repo with user repo"):
            with (
                environment.get_snapshot_guard().read_lock()
                if isinstance(environment, DockerEnvironment)
                else no_op_context_manager()
            ):
                process: RunningProcess = run_background(
                    [
                        "rsync",
                        "-r",
                        "--rsync-path=/imbue/nix_bin/rsync",
                        f"--exclude-from={f.name}",
                        "-e",
                        f"{get_sculptor_folder() / 'ssh' / 'ssh'} -p {environment.server_port_by_name[SSHD_SERVER_NAME]}",
                        f"{user_repo_path}/.git/",
                        f"{SCULPTOR_USER}@localhost:{str(ENVIRONMENT_WORKSPACE_DIRECTORY).rstrip('/')}/.git/",
                        # f"{user_repo_path}/",
                        # f"{SCULPTOR_USER}@localhost:{str(ENVIRONMENT_WORKSPACE_DIRECTORY).rstrip('/')}/",
                    ],
                    cwd=user_repo_path,
                    is_checked=True,
                )
                with timeout_monitor(
                    timeout=30,
                    on_timeout=lambda timeout: _send_warning_message(
                        task_id,
                        f"Rsyncing in-container repo with user repo is taking longer than expected ({timeout}s)",
                        services,
                    )
                    if task_id is not None and services is not None
                    else None,
                ):
                    process.wait(timeout=300)
                # if we're keeping uncommitted, then we need to sync from the special folder
                if task_id_if_keep_uncommitted is not None:
                    copy_of_user_repo_path = (
                        get_sculptor_folder() / "user_repo_copies" / str(task_id_if_keep_uncommitted)
                    )
                    current_state_sync_process: RunningProcess = run_background(
                        [
                            "rsync",
                            "-r",
                            "--rsync-path=/imbue/nix_bin/rsync",
                            f"--exclude-from={f.name}",
                            "-e",
                            f"{get_sculptor_folder() / 'ssh' / 'ssh'} -p {environment.server_port_by_name[SSHD_SERVER_NAME]}",
                            f"{str(copy_of_user_repo_path).rstrip('/')}/",
                            f"{SCULPTOR_USER}@localhost:{str(ENVIRONMENT_WORKSPACE_DIRECTORY).rstrip('/')}/",
                        ],
                        cwd=copy_of_user_repo_path,
                        is_checked=True,
                    )
                    with timeout_monitor(
                        timeout=30,
                        on_timeout=lambda timeout: _send_warning_message(
                            task_id,
                            f"Rsyncing (part 2) in-container repo with user repo is taking longer than expected ({timeout}s)",
                            services,
                        )
                        if task_id is not None and services is not None
                        else None,
                    ):
                        current_state_sync_process.wait(timeout=300)


@contextmanager
def no_op_context_manager():
    yield


@contextmanager
def message_queue_context(
    task: Task, task_state: AgentTaskStateV1, services: ServiceCollectionForTask
) -> Generator[
    tuple[Queue[Message], ChatInputUserMessage, ForkAgentSystemMessage | None],
    None,
    None,
]:
    """Subscribe to messages and wait for initial/fork messages."""
    with services.task_service.subscribe_to_user_and_sculptor_system_messages(task.object_id) as input_message_queue:
        # Wait for the initial user message
        initial_message = _wait_for_initial_user_message(
            user_message_queue=input_message_queue, task_id=task.object_id
        )

        # Handle fork message if this is a forked task
        parent_id = task.parent_task_id
        if parent_id is None:
            fork_message = None
        else:
            fork_message = _wait_for_fork_message(parent_id, input_message_queue)

        # Wait for the initial user message
        initial_message = _wait_for_initial_user_message(
            user_message_queue=input_message_queue, task_id=task.object_id
        )

        # Discard already processed messages
        _drop_already_processed_messages(task_state.last_processed_message_id, input_message_queue)

        yield input_message_queue, initial_message, fork_message


@contextmanager
def branch_prediction_context(
    task: Task,
    task_state: AgentTaskStateV1,
    initial_message: ChatInputUserMessage,
    project: Project,
    services: ServiceCollectionForTask,
    settings: SculptorSettings,
) -> Generator[tuple[list[tuple[str, str]], Thread | None], None, None]:
    """Start branch name prediction thread if needed."""
    title_and_branch_container: list[tuple[str, str]] = []
    title_thread = None

    if task_state.title is None or task_state.branch_name is None:
        with services.git_repo_service.open_local_user_git_repo_for_read(task.user_reference, project) as repo:
            branches_in_user_repo = repo.get_recent_branches()

        existing_branches = sorted(branches_in_user_repo)

        anthropic_credentials = services.anthropic_credentials_service.get_anthropic_credentials()
        # assert anthropic_credentials is not None

        title_thread = ObservableThread(
            target=_predict_branch_name,
            args=(
                initial_message.text,
                existing_branches,
                title_and_branch_container,
                settings,
                anthropic_credentials,
            ),
        )
        title_thread.start()

    try:
        yield title_and_branch_container, title_thread
    finally:
        # Ensure thread is cleaned up if still running
        if title_thread and title_thread.is_alive():
            title_thread.join()


@contextmanager
def environment_setup_context(
    project: Project,
    task: Task,
    task_data: AgentTaskInputsV1,
    task_state: AgentTaskStateV1,
    services: ServiceCollectionForTask,
    secrets: Mapping[str, str | Secret],
) -> Generator[tuple[Environment, AgentTaskStateV1], None, None]:
    """Set up the environment with the appropriate image."""
    # if we have an existing environment, try to reuse it
    environment: Environment | None = None
    used_old_env = False
    try:
        if task_state.environment_id is None:
            raise EnvironmentNotFoundError()

        environment = services.environment_service.create_environment(
            task_state.environment_id,
            config=task_data.environment_config,
            name=str(task.object_id),
            project_id=project.object_id,
        )
        used_old_env = True
    except (EnvironmentNotFoundError, EnvironmentConfigurationChangedError) as e:
        if isinstance(e, EnvironmentNotFoundError):
            logger.debug("Unable to start previous container because env was not found: {}", e)
        elif isinstance(e, EnvironmentConfigurationChangedError):
            logger.debug("Unable to start previous container because env config changed: {}", e)
        else:
            logger.debug("Unable to start previous container because: {}", e)
        # otherwise, ensure we have an image
        image, task_state = _ensure_image(
            secrets, services, task_data.image_config, task.object_id, project, task_state
        )

        # Create the environment
        with timeout_monitor(
            timeout=_ENVIRONMENT_CREATION_TIMEOUT_SECONDS,
            on_timeout=lambda timeout: _send_warning_message(
                task.object_id,
                f"Environment creation is taking longer than expected ({timeout}s)",
                services,
            ),
        ):
            environment = services.environment_service.create_environment(
                image,
                config=task_data.environment_config,
                name=str(task.object_id),
                project_id=project.object_id,
            )
    # just for pycharm, sigh
    assert environment is not None
    is_create_message_sent = False
    try:
        if task_state.last_processed_message_id is None:
            if not used_old_env:
                task_id_if_keep_uncommitted = None if task_data.is_git_state_clean else task.object_id
                hard_overwrite_full_agent_workspace(
                    environment=environment,
                    user_repo_path=Path(urlparse(project.user_git_repo_url).path),
                    task_id=task.object_id,
                    services=services,
                    task_id_if_keep_uncommitted=task_id_if_keep_uncommitted,
                )
        with services.data_model_service.open_task_transaction() as transaction:
            # emit a message
            services.task_service.create_message(
                EnvironmentCreatedRunnerMessage(environment=environment), task.object_id, transaction
            )
            # save the environment into the task state so we can resume
            if task_state.environment_id != environment.environment_id:
                task_state = task_state.evolve(task_state.ref().environment_id, environment.environment_id)
                task = task.evolve(task.ref().current_state, task_state.model_dump())
                task = transaction.upsert_task(task)
        is_create_message_sent = True
        with logger.contextualize(environment=environment.get_extra_logger_context()):
            logger.debug("created environment")
            yield environment, task_state
    finally:
        should_destroy = False
        with services.data_model_service.open_task_transaction() as transaction:
            updated_task = transaction.get_task(task.object_id)
            if updated_task is not None:
                assert isinstance(updated_task.current_state, AgentTaskStateV1)
                if updated_task.current_state.environment_id != environment.environment_id:
                    should_destroy = True
            if is_create_message_sent:
                services.task_service.create_message(EnvironmentStoppedRunnerMessage(), task.object_id, transaction)
        environment.close()
        # if the task is no longer tied to this environment, there's no reason to keep this environment around
        # because it will never be reused. This could come about as a result of failure to persist the environment
        if should_destroy:
            environment.destroy()


def finalize_git_setup(
    task: Task,
    task_state: AgentTaskStateV1,
    environment: Environment,
    fork_message: ForkAgentSystemMessage | None,
    title_thread: Thread | None,
    title_and_branch_container: list[tuple[str, str]],
    initial_message: ChatInputUserMessage,
    project: Project,
    task_data: AgentTaskInputsV1,
    services: ServiceCollectionForTask,
    bare_repo_path: Path | None = None,
) -> AgentTaskStateV1:
    """Handle the final git setup steps after environment is ready."""
    if title_thread is None:
        # Branch name already exists
        assert task_state.branch_name is not None
        full_branch_name = task_state.branch_name

        # Handle forked task branch setup
        if fork_message is not None:
            logger.debug("Ensuring that we are on the right branch for a forked task")
            _, stdout, _ = run_git_command_in_environment(
                environment,
                ["/imbue/nix_bin/git", "rev-parse", "--abbrev-ref", "HEAD"],
                {},
                check_output=True,
            )
            current_branch = stdout.strip()
            if current_branch != full_branch_name:
                logger.debug("Checking out the right branch: {}", full_branch_name)
                run_git_command_in_environment(
                    environment,
                    ["git", "checkout", "-b", full_branch_name],
                    {},
                    check_output=True,
                    is_retry_safe=True,
                )
    else:
        # Initialize git if needed
        user_config = get_user_config_instance()
        # Use user config values if available, otherwise fall back to default
        if user_config and user_config.user_email:
            email = user_config.user_email
            username = user_config.user_git_username
        else:
            email = "sculptor@imbue.com"
            username = "Sculptor"

        git_config_command = [
            "bash",
            "-c",
            f"git config --global user.email {email} && git config --global user.name '{username}'",
        ]
        run_git_command_in_environment(environment, git_config_command, {}, check_output=True)

        # Resolve branch prediction and checkout
        full_branch_name, task_state = _resolve_branch_name_prediction_thread_and_checkout_branch(
            title_and_branch_container=title_and_branch_container,
            title_thread=title_thread,
            task_id=task.object_id,
            user_reference=task.user_reference,
            project=project,
            task_state=task_state,
            initial_message=initial_message,
            environment=environment,
            git_hash=task_data.git_hash,
            services=services,
            keep_uncommitted=not task_data.is_git_state_clean,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futs = []
        file_content_by_relative_path = {
            SOURCE_BRANCH_STATE_FILE: task_data.initial_branch,
            TASK_BRANCH_STATE_FILE: full_branch_name,
            INITIAL_GIT_HASH_STATE_FILE: task_data.git_hash,
        }

        telemetry_task_info_contents = _get_telemetry_task_info_contents(task.object_id, project)
        if telemetry_task_info_contents is not None:
            file_content_by_relative_path[TELEMETRY_TASK_INFO_JSON_STATE_FILE] = telemetry_task_info_contents
        futs.append(executor.submit(_write_initial_state_to_file, environment, file_content_by_relative_path))

        for future in as_completed(futs):
            future.result()

    return task_state


# TODO(PROD-1416): Is there a test that tests this handoff from Sculptor to container?
def _get_telemetry_task_info_contents(task_id: TaskID, project: Project) -> str | None:
    telemetry_info = get_telemetry_info()
    if telemetry_info is not None:
        original_git_repo_url = None
        if project.user_git_repo_url and project.user_git_repo_url.startswith("file://"):
            try:
                repo_path = Path(project.user_git_repo_url.replace("file://", ""))
                original_git_repo_url = get_repo_url_from_folder(repo_path)
                original_git_repo_url = sanitize_git_url_robust(original_git_repo_url)
            except Exception as e:
                logger.info("Failed to get upstream URL for {}: {}", project.user_git_repo_url, e)
                original_git_repo_url = sanitize_git_url_robust(project.user_git_repo_url)
        else:
            original_git_repo_url = sanitize_git_url_robust(project.user_git_repo_url)

        telemetry_project_info = TelemetryProjectInfo(
            telemetry_info=telemetry_info,
            project_id=str(project.object_id),
            gitlab_mirror_repo_url=project.our_git_repo_url,
            original_git_repo_url=original_git_repo_url,
        )
        telemetry_task_info = TelemetryTaskInfo(telemetry_project_info=telemetry_project_info, task_id=task_id)
        logger.info("Providing telemetry task info: model_dump={}", telemetry_task_info.model_dump())
        return telemetry_task_info.model_dump_json()
    return None


def _resolve_branch_name_prediction_thread_and_checkout_branch(
    user_reference: UserReference,
    project: Project,
    title_thread: Thread,
    title_and_branch_container: list[tuple[str, str]],
    task_id: TaskID,
    task_state: AgentTaskStateV1,
    initial_message: ChatInputUserMessage,
    environment: Environment,
    git_hash: str,
    services: ServiceCollectionForTask,
    keep_uncommitted: bool,
) -> tuple[str, AgentTaskStateV1]:
    """
    Waits (a little while) for the title prediction thread to finish,
    then saves the title and branch name to the database.
    """
    title_thread.join(timeout=_TITLE_NAME_TIMEOUT_SECONDS)
    if title_thread.is_alive():
        branch_suffix = _get_random_branch_name()
        logger.warning("Title prediction thread did not finish in time, using defaults")
        title, full_branch_name = initial_message.text, f"sculptor/{branch_suffix}"
    else:
        title, full_branch_name = only(title_and_branch_container)
    with services.git_repo_service.open_local_user_git_repo_for_write(user_reference, project) as user_repo:
        # first make sure this branch exists in the user's repo
        logger.info("Attempting to create branch on user's repo: {}", full_branch_name)
        returncode, _, _ = run_git_command_local(
            ["git", "branch", full_branch_name, git_hash],
            cwd=user_repo.get_repo_path(),
            check_output=False,
            is_retry_safe=False,  # Creating a branch is not idempotent
        )
        if returncode != 0:
            # this branch name is already taken, so we need to get a new one
            full_branch_name = f"sculptor/{_get_random_branch_name()}"
            run_git_command_local(
                ["git", "branch", full_branch_name, git_hash],
                cwd=user_repo.get_repo_path(),
                check_output=True,
                is_retry_safe=False,  # Creating a branch is not idempotent
            )
            logger.info("Branch name already taken, using new one: {}", full_branch_name)
        # now get the agent to be up-to-date
        if keep_uncommitted:
            # will already have been synced in earlier, so we should be at the exact state that we want
            # however, logically we want the agent to be on a particular branch
            # thus, the easy thing to do is simply run git checkout -b <branch_name>
            # however, this can fail if you are in the middle of a merge/rebase/etc
            # in such cases, we *allow* this command to fail,
            # and simply tell the agent to remember that it's supposed to be on "sculptor/" prefixed branch names
            try:
                environment.run_process_to_completion(
                    ["git", "checkout", "-b", full_branch_name],
                    secrets={},
                    cwd=str(ENVIRONMENT_WORKSPACE_DIRECTORY),
                )
            except ProcessError as e:
                if e.returncode is not None:
                    # any exit code is fine, we tried our best
                    logger.debug("Failed to checkout branch with uncommitted changes, proceeding anyway: {}", e)
                else:
                    raise
        else:
            # Fetch the branch from the user's repo to the environment
            logger.info("Fetching branch from user's repo to environment: {}", full_branch_name)
            environment.push_into_environment_repo(user_repo.get_repo_path(), full_branch_name, full_branch_name)
            # now, we need to hard reset the environment to this branch
            environment.run_process_to_completion(
                ["bash", "-c", f"git reset --hard && git clean -fd && git checkout {full_branch_name}"],
                secrets={},
                cwd=str(ENVIRONMENT_WORKSPACE_DIRECTORY),
            )
        logger.info("Done fetching branch from user's repo to environment")

    mutable_task_state = evolver(task_state)
    assign(mutable_task_state.title, lambda: title)
    task_repo_path = ENVIRONMENT_WORKSPACE_DIRECTORY
    assign(mutable_task_state.task_repo_path, lambda: task_repo_path)
    assign(mutable_task_state.branch_name, lambda: full_branch_name)
    task_state = chill(mutable_task_state)

    # might as well commit our progress
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task_id)
        assert task_row is not None
        task_row = task_row.evolve(task_row.ref().current_state, task_state.model_dump())
        _task_row = transaction.upsert_task(task_row)
    return full_branch_name, task_state


def _predict_branch_name(
    initial_prompt: str,
    existing_branches: Sequence[str],
    title_and_branch_container: list[tuple[str, str]],
    settings: SculptorSettings,
    anthropic_credentials: AnthropicCredentials,
) -> None:
    if settings.TESTING.INTEGRATION_ENABLED:
        title_and_branch_container.append(_generate_fixed_title_and_branch_for_testing())
        return
    try:
        logger.debug("Found {} existing branches in repository", len(existing_branches))
        logger.info("Generating title and branch name for task...")
        title_and_branch = generate_title_and_branch_from_initial_prompt(
            initial_prompt,
            existing_branches,
            anthropic_credentials,
        )
        title = title_and_branch.title
        branch_suffix = title_and_branch.branch_name
        if branch_suffix in existing_branches:
            branch_suffix = _get_random_branch_name()
        full_branch_name = f"sculptor/{branch_suffix}"
        logger.info("Generated title: '{}' and branch: '{}'", title, full_branch_name)
        title_and_branch_container.append((title, full_branch_name))
        emit_posthog_event(
            PosthogEventModel(
                name=SculptorPosthogEvent.TASK_PREDICT_BRANCH_NAME,
                component=ProductComponent.TASK,
                payload=title_and_branch,
            )
        )
    except Exception as e:
        log_exception(
            e,
            "Failed to generate title and branch name",
            priority=ExceptionPriority.LOW_PRIORITY,
        )
        title = generate_title_only_from_initial_prompt(
            initial_prompt,
            existing_branches,
            anthropic_credentials,
        )
        logger.info("Generated fallback title: '{}'", title)
        full_branch_name = f"sculptor/{_get_random_branch_name()}"
        title_and_branch_container.append((title, full_branch_name))


def _generate_fixed_title_and_branch_for_testing() -> tuple[str, str]:
    global _FIXED_BRANCH_NAME_COUNTER_FOR_TESTING
    _FIXED_BRANCH_NAME_COUNTER_FOR_TESTING += 1
    return (
        f"Task {_FIXED_BRANCH_NAME_COUNTER_FOR_TESTING}",
        f"branch_{_FIXED_BRANCH_NAME_COUNTER_FOR_TESTING}",
    )


def _get_random_branch_name() -> str:
    return coolname.generate_slug(3)


def load_initial_task_state(services: ServiceCollectionForTask, task: Task) -> tuple[AgentTaskStateV1, Project]:
    logger.info("loading initial task state (if any)")
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task.object_id)
        assert task_row is not None, "Task must exist in the database"
        if task_row.current_state is None:
            logger.debug("no current state found, creating a new one")
            task_state = AgentTaskStateV1()
        else:
            logger.debug("found existing task state, loading it...")
            task_state = AgentTaskStateV1.model_validate(task_row.current_state)
        # load the project so that we can figure out the repo path as well
        project = transaction.get_project(task.project_id)
        assert project is not None, "Project must exist in the database"
    return task_state, project


def _send_warning_message(
    task_id: TaskID,
    message: str,
    services: ServiceCollectionForTask,
    error: Exception | None = None,
) -> None:
    with services.data_model_service.open_task_transaction() as transaction:
        logger.warning(message, exc_info=error)
        serialized_error = SerializedException.build(error) if error is not None else None
        warning_message = WarningRunnerMessage(message=message, error=serialized_error)
        if not is_running_within_a_pytest_tree():
            services.task_service.create_message(warning_message, task_id, transaction)


def _ensure_image(
    secrets: Mapping[str, str | Secret],
    services: ServiceCollectionForTask,
    image_config: "ImageConfigTypes",
    task_id: TaskID,
    project: Project,
    task_state: AgentTaskStateV1,
) -> tuple[ImageTypes, AgentTaskStateV1]:
    image = task_state.image

    if image is None:
        with logger.contextualize(log_type=USER_FACING_LOG_TYPE, task_id=task_id):
            logger.debug("creating image")
        with timeout_monitor(
            timeout=_IMAGE_CREATION_TIMEOUT_SECONDS,
            on_timeout=lambda timeout: _send_warning_message(
                task_id,
                f"Image creation is taking longer than expected ({timeout}s)",
                services,
            ),
        ):
            active_repo_path = Path(urlparse(project.user_git_repo_url).path)
            cached_repo_path = project.get_cached_repo_path()
            # FIXME: it seems like this might be fragile if tasks are allowed different configs/secrets since we cache on project id elsewhere
            image = services.environment_service.ensure_image(
                config=image_config,
                active_repo_path=active_repo_path,
                cached_repo_path=cached_repo_path,
                secrets=secrets,
                project_id=project.object_id,
            )

        with logger.contextualize(log_type=USER_FACING_LOG_TYPE, task_id=task_id):
            logger.debug("created image: {}", image)

        task_state = task_state.evolve(task_state.ref().image, image)
        with services.data_model_service.open_task_transaction() as transaction:
            task_row = transaction.get_task(task_id)
            assert task_row is not None
            task_row = task_row.evolve(task_row.ref().current_state, task_state)
            _updated_task_row = transaction.upsert_task(task_row)
    else:
        with logger.contextualize(log_type=USER_FACING_LOG_TYPE, task_id=task_id):
            logger.debug("using existing image: {}", image)
    return image, task_state


def _drop_already_processed_messages(
    last_processed_input_message_id: AgentMessageID | None,
    user_message_queue: Queue[Message],
) -> list[Message]:
    """
    Drops all user messages that have already been processed by the agent.
    Return the dropped messages as well as the messages that will be re-queued.
    """
    # catch up, if necessary, to where we were last time
    messages_so_far: list[Message] = []
    if last_processed_input_message_id is not None:
        while not user_message_queue.empty():
            message = user_message_queue.get()
            messages_so_far.append(message)
            if message.message_id == last_processed_input_message_id:
                break
    return messages_so_far


def _wait_for_initial_user_message(user_message_queue: Queue[Message], task_id: TaskID) -> ChatInputUserMessage:
    """
    Waits for the first user message AFTER the most recent fork message if it exists OR the start of the task.
    """
    logger.trace("user message queue: {}", user_message_queue.queue)
    while True:
        user_input_message: ChatInputUserMessage | None = None
        for i in range(user_message_queue.qsize() - 1, -1, -1):
            message = user_message_queue.queue[i]
            if isinstance(message, ForkAgentSystemMessage):
                # Ensure that this is a forked *from* message
                if message.child_task_id != task_id:
                    continue
                if user_input_message is not None:
                    return user_input_message
                break
            elif isinstance(message, ChatInputUserMessage):
                user_input_message = message
        if user_input_message is not None:
            return user_input_message
        time.sleep(_POLL_SECONDS)


def _wait_for_fork_message(parent_id: TaskID, user_message_queue: Queue[Message]) -> ForkAgentSystemMessage:
    logger.trace("user message queue: {}", user_message_queue.queue)
    while True:
        for i in range(0, user_message_queue.qsize()):
            message = user_message_queue.queue[i]
            if isinstance(message, ForkAgentSystemMessage):
                if message.parent_task_id == parent_id:
                    return message
        time.sleep(_POLL_SECONDS)


def _write_initial_state_to_file(environment: Environment, file_content_by_relative_path: Mapping[str, str]) -> None:
    state_path = environment.get_state_path()
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(environment.write_file, str(state_path / relative_path), content)
            for relative_path, content in file_content_by_relative_path.items()
        }
        for future in as_completed(futures):
            future.result()
