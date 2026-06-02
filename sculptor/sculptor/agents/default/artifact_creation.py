import json
import sys
from pathlib import Path
from queue import Queue

from loguru import logger
from pydantic import AnyUrl
from pydantic import ValidationError

from sculptor.agents.default.constants import FILE_CHANGE_TOOL_NAMES
from sculptor.agents.default.utils import get_warning_message
from sculptor.database.models import AgentMessageID
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.common import generate_id
from sculptor.foundation.constants import ExceptionPriority
from sculptor.interfaces.agents.agent import TaskID
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import WarningAgentMessage
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import ArtifactUnion
from sculptor.interfaces.agents.artifacts import FileAgentArtifact
from sculptor.interfaces.agents.artifacts import Task
from sculptor.interfaces.agents.artifacts import TaskListArtifact
from sculptor.interfaces.agents.errors import IllegalOperationError
from sculptor.interfaces.agents.harness import Harness
from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.state.chat_state import ToolInput
from sculptor.utils.timeout import log_runtime_decorator


@log_runtime_decorator()
def get_file_artifact_messages(
    artifact_name: str,
    environment: AgentExecutionEnvironment,
    harness: Harness,
    task_id: TaskID,
    session_id: str | None = None,
) -> list[UpdatedArtifactAgentMessage | WarningAgentMessage]:
    messages: Queue[UpdatedArtifactAgentMessage | WarningAgentMessage] = Queue()
    try:
        remote_artifact_path = _make_file_artifact(
            artifact_name=artifact_name,
            environment=environment,
            harness=harness,
            session_id=session_id,
        )
    except Exception as e:
        log_exception(
            e,
            "Failed to create file artifact {artifact_name}",
            priority=ExceptionPriority.MEDIUM_PRIORITY,
            artifact_name=artifact_name,
        )
        messages.put(get_warning_message(f"Failed to create file artifact {artifact_name}", e, task_id))
    else:
        file_artifact_message = UpdatedArtifactAgentMessage(
            message_id=AgentMessageID(),
            artifact=FileAgentArtifact(
                name=artifact_name,
                url=AnyUrl(f"file://{remote_artifact_path}"),
            ),
        )
        messages.put(file_artifact_message)
    return list(messages.queue)


def should_send_diff_and_branch_name_artifacts(tool_name: str, tool_input: ToolInput) -> bool:
    logger.info("Should send diff and branch name")
    if tool_name in (FILE_CHANGE_TOOL_NAMES + (AgentToolName.BASH,)):
        return True
    command = tool_input.get("command", "")
    # Check for git commands that change the branch state
    git_branch_commands = [
        "git commit",
        "git reset",
        "git revert",
        "git checkout",
        "git switch",
        "git merge",
        "git rebase",
        "git cherry-pick",
    ]

    return any(cmd in command for cmd in git_branch_commands)


def should_refresh_task_list(tool_name: str) -> bool:
    """Whether a tool_result for this tool should re-read the per-task JSON store."""
    return tool_name in (AgentToolName.TASK_CREATE, AgentToolName.TASK_UPDATE)


def _task_sort_key(task: Task) -> int:
    try:
        return int(task.id)
    except (TypeError, ValueError):
        return sys.maxsize


def _read_task_list_artifact(
    environment: AgentExecutionEnvironment,
    harness: Harness,
    session_id: str | None,
) -> TaskListArtifact:
    """Build a TaskListArtifact by enumerating per-task JSON files.

    Returns an empty artifact when the session id is unknown or the tasks
    directory does not exist. Per-file parse failures are logged and the
    file is skipped so one corrupt file cannot blank the whole list.

    The tasks directory lives under ``$HOME/.claude/tasks/{session_id}/``,
    outside the agent's workspace. LocalEnvironment.{exists,read_file} remap
    any path that is not under the workspace into the workspace root, so we
    operate on the returned Path directly rather than going through the
    environment's file primitives.
    """
    if session_id is None:
        return TaskListArtifact(tasks=[])

    tasks_dir = harness.get_tasks_path(environment, session_id)
    if tasks_dir is None or not tasks_dir.is_dir():
        return TaskListArtifact(tasks=[])

    tasks: list[Task] = []
    for entry in tasks_dir.iterdir():
        if entry.suffix != ".json":
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            tasks.append(Task.model_validate(data))
        except (json.JSONDecodeError, ValidationError, OSError) as e:
            logger.info("Skipping malformed task file {}: {}", entry, e)
            continue

    tasks.sort(key=_task_sort_key)
    return TaskListArtifact(tasks=tasks)


def _make_file_artifact(
    artifact_name: str,
    environment: AgentExecutionEnvironment,
    harness: Harness,
    session_id: str | None = None,
) -> Path:
    """Generates artifacts of type artifact_name and saves them into target_file"""
    target_file = environment.get_artifacts_path() / f"{artifact_name}-{generate_id()}"

    artifact: ArtifactUnion
    if artifact_name == ArtifactType.PLAN:
        artifact = _read_task_list_artifact(environment, harness, session_id)
        json_content = artifact.model_dump_json(indent=2)
        environment.write_file(str(target_file), json_content)
    else:
        raise IllegalOperationError(f"Unknown artifact name: {artifact_name}")

    assert environment.exists(str(target_file)), f"Artifact {target_file} does not exist"
    return target_file
