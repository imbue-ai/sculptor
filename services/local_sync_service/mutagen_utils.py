import os
from pathlib import Path
from typing import Callable
from typing import Sequence

from loguru import logger
from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import run_background
from imbue_core.processes.local_process import run_blocking
from imbue_core.retry_utils import log_error_before_sleep
from imbue_core.subprocess_utils import FinishedProcess
from imbue_core.subprocess_utils import ProcessError
from imbue_core.subprocess_utils import ProcessTimeoutError
from sculptor.services.local_sync_service.local_sync_errors import MutagenSyncError
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.read_write_lock import ReadWriteLock


def mutagen_sync_name_for(project_id: ProjectID, task_id: TaskID) -> str:
    sanitized_task_id = str(task_id).replace("_", "-")
    sanitized_project_id = str(project_id).replace("_", "-")
    return f"sculptor-{sanitized_project_id}-{sanitized_task_id}"


def terminate_mutagen_session(session_name: str, is_missing_ok: bool = True) -> None:
    """Terminate a mutagen sync session."""
    try:
        # TODO: why would this hange forever (see https://imbue-ai.slack.com/archives/C034US10UKY/p1756499446890219)
        run_mutagen_cmd(command=["mutagen", "sync", "terminate", session_name], timeout=5.0)
    except ProcessError as e:
        if is_missing_ok and "unable to locate requested sessions" in e.stderr:
            logger.debug("Mutagen session {} not found to terminate", session_name)
            return
        # Don't raise for terminate failures - session may not exist
        logger.error(
            "Failed to terminate mutagen session '{}' (is_timed_out={}): stdout={} stderr={}",
            session_name,
            isinstance(e, ProcessTimeoutError),
            e.stdout,
            e.stderr,
        )


def stop_mutagen_daemon() -> None:
    """Terminate a mutagen daemon if running."""
    try:
        run_mutagen_cmd(command=["mutagen", "daemon", "stop"], timeout=5.0)
    except ProcessError as e:
        user_debug_command = "=".join(_mutagen_data_directory_env()) + " mutagen daemon stop"
        advice = (
            "If you are seeing this, don't worry - it won't cause any problems.",
            "To stop the mutagen daemon manually, run:",
            user_debug_command,
        )
        log_exception(
            e,
            "mutagen daemon stop failed:\n{out}\n{err}.\n{advice}",
            priority=ExceptionPriority.MEDIUM_PRIORITY,
            out=e.stdout,
            err=e.stderr,
            advice="\n".join(advice),
        )


def get_all_sculptor_mutagen_session_names(prefix: str = "sculptor-") -> tuple[str, ...]:
    """Get all mutagen sync sessions that are managed by Sculptor."""
    cursed_name_extracting_go_template = r'{{range .}}{{.Name}}{{"\n"}}{{end}}'
    list_all_sessions = ["mutagen", "sync", "list", "--template", cursed_name_extracting_go_template]
    try:
        result = run_mutagen_cmd(command=list_all_sessions, timeout=5.0)
        lines_that_are_names = result.stdout.strip().split("\n")
        return tuple(name.strip() for name in lines_that_are_names if name.startswith(prefix))
    except ProcessError as e:
        logger.error(
            "Failed to list mutagen sync sessions (is_timed_out={}): stdout={} stderr={}",
            isinstance(e, ProcessTimeoutError),
            e.stdout,
            e.stderr,
        )
        return ()


def get_all_sculptor_mutagen_sessions_for_projects(
    get_project_ids: Callable[[], tuple[ProjectID, ...]],
) -> tuple[str, ...]:
    """Get all mutagen sync sessions for the given project_id."""
    sculptor_session_names = get_all_sculptor_mutagen_session_names()
    if not sculptor_session_names:
        return ()
    search_prefixes = tuple(f"sculptor-{project_id}-".replace("_", "-") for project_id in get_project_ids())
    return tuple(
        session for session in sculptor_session_names if any(session.startswith(prefix) for prefix in search_prefixes)
    )


def _mutagen_data_directory_env() -> tuple[str, str]:
    return "MUTAGEN_DATA_DIRECTORY", str((get_sculptor_folder() / "mutagen").expanduser())


def run_mutagen_cmd(
    command: Sequence[str], timeout: float | None = None, snapshot_guard: ReadWriteLock | None = None
) -> FinishedProcess:
    command = tuple(command)
    new_environ = os.environ.copy()
    # We need to set a new data directory because the MUTAGEN_SSH_PATH
    # affects the entire mutagen daemon, not just one particular sync.
    # Setting MUTAGEN_DATA_DIRECTORY lets us set a temporary SSH path without
    # restarting the daemon used by the user's other mutagen sessions.
    data_dir_env, data_dir_value = _mutagen_data_directory_env()
    new_environ[data_dir_env] = data_dir_value
    new_environ["MUTAGEN_SSH_PATH"] = str((get_sculptor_folder() / "ssh").expanduser())
    if snapshot_guard:
        with snapshot_guard.read_lock():
            process = run_background(command=command, env=new_environ, timeout=timeout, is_checked=True)
        process.wait()
        finished_process = FinishedProcess(
            command=command,
            returncode=process.returncode,
            stdout=process.read_stdout(),
            stderr=process.read_stderr(),
            is_timed_out=process.get_timed_out(),
            is_output_already_logged=False,
        )
    else:
        finished_process = run_blocking(command=command, env=new_environ, timeout=timeout)
    return finished_process


@retry(
    retry=retry_if_exception(lambda e: True),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before_sleep=log_error_before_sleep,
)
def create_controlled_mutagen_sync(
    session_name: str,
    sync_mode: str,
    source_path_or_url: str,
    dest_path_or_url: str,
    ignore_patterns: Sequence[str],
    is_including_git_state_with_no_hooks: bool = False,
    snapshot_guard: ReadWriteLock | None = None,
) -> None:
    """Create a no-watch mutagen sync session with the specified parameters"""

    cmd = [
        "mutagen",
        "sync",
        "create",
        "--watch-mode",
        "no-watch",
        "--name",
        session_name,
        "--sync-mode",
        sync_mode,
    ] + (["--ignore-vcs"] if not is_including_git_state_with_no_hooks else ["--ignore", ".git/hooks"])
    for pattern in ignore_patterns:
        cmd.extend(["--ignore", pattern])

    cmd.extend([source_path_or_url, dest_path_or_url])
    try:
        run_mutagen_cmd(cmd, snapshot_guard=snapshot_guard)
    except ProcessError as e:
        logger.debug("Failed to create mutagen session")
        raise MutagenSyncError(
            "Failed to create mutagen sync session",
            operation="create",
            session_name=session_name,
            sync_mode=sync_mode,
            source_path=str(source_path_or_url),
            dest_path=str(dest_path_or_url),
            exit_code=e.returncode,
            stderr=e.stderr,
        ) from e


def _convert_git_ignore_pattern_to_mutagen_ignore_pattern(pattern: str) -> str:
    # TODO: do a more thorough conversion if needed
    return pattern


def get_git_ignored_patterns_for_mutagen(repo_path: Path) -> list[str]:
    """Get ignored patterns using git's native ignore logic.

    Uses 'git status --ignored=matching' to get files that are currently ignored
    by git (including all recursive .gitignore files). Since mutagen format is
    "almost identical" to git's, we can use these paths directly as patterns.
    """
    patterns = []
    get_ignored_patterns = ("git", "status", "--ignored=matching", "--porcelain")

    try:
        # Use git status to get ignored files
        result = run_blocking(
            command=list(get_ignored_patterns),
            cwd=repo_path,
            timeout=30.0,
        )
        lines_that_are_patterns = result.stdout.strip().split("\n")
        for line in lines_that_are_patterns:
            if line.startswith("!! "):
                # Extract the file path (everything after "!! ")
                ignored_path = line[3:]
                patterns.append(_convert_git_ignore_pattern_to_mutagen_ignore_pattern(ignored_path))

    except ProcessError as e:
        logger.error("Failed to get ignored files from git: {}", e)

    return patterns
