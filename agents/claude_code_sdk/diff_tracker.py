import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import run_blocking
from imbue_core.sculptor.state.chat_state import ToolInput
from imbue_core.subprocess_utils import ProcessError
from sculptor.agents.claude_code_sdk.constants import FILE_CHANGE_TOOL_NAMES
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.tasks.handlers.run_agent.errors import GitCommandFailure
from sculptor.tasks.handlers.run_agent.git import run_git_command_in_environment


def _run_git_command_in_environment_and_handle_errors(
    environment: Environment,
    command: list[str],
    error_message: str,
    extra: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[int, str, str] | None:
    try:
        return run_git_command_in_environment(
            environment=environment,
            command=command,
            check_output=True,
            timeout=timeout,
        )
    except Exception as e:
        log_exception(
            exc=e,
            message=error_message,
            priority=ExceptionPriority.LOW_PRIORITY,
            extra=extra,
        )
        return None


def _is_file_present_at_commit_hash(environment: Environment, commit_hash: str, relative_file_path: Path) -> bool:
    result = _run_git_command_in_environment_and_handle_errors(
        environment=environment,
        command=["git", "ls-tree", commit_hash, "--", str(relative_file_path)],
        error_message=f"Failed to check if {relative_file_path} was present at commit hash {commit_hash}",
        extra=dict(filepath=relative_file_path, initial_tree_sha=commit_hash),
    )

    if not result:
        return False

    returncode, stdout, _ = result
    return returncode == 0 and stdout.strip() != ""


def _get_file_contents_at_commit_hash(
    environment: Environment, commit_hash: str, relative_file_path: Path
) -> str | None:
    result = _run_git_command_in_environment_and_handle_errors(
        environment=environment,
        command=["git", "show", f"{commit_hash}:{relative_file_path}"],
        error_message=f"Failed to get file {relative_file_path} from git tree {commit_hash}",
        extra=dict(filepath=relative_file_path, initial_tree_sha=commit_hash),
    )

    if not result:
        return None

    _, stdout, _ = result
    return stdout.strip()


class DiffTracker:
    """Tracks file changes and computes diffs using in-memory snapshots."""

    def __init__(self, environment: Environment, initial_tree_sha: str | None = None) -> None:
        self.environment = environment
        self.workspace_path = environment.get_workspace_path()
        self.file_snapshot_by_path: dict[str, str | bytes | None] = {}
        self.initial_tree_sha = initial_tree_sha

    def update_initial_tree_sha(self, new_tree_sha: str) -> None:
        """Update the initial git tree SHA and clear snapshots."""
        self.initial_tree_sha = new_tree_sha
        self.file_snapshot_by_path.clear()
        logger.debug("Updated initial_tree_sha to {}, cleared file snapshots", new_tree_sha)

    def _get_file_from_git_tree(self, file_path: str) -> str | bytes | None:
        """Get file content from the initial git tree SHA."""
        if not self.initial_tree_sha:
            return None

        if file_path.startswith(str(self.workspace_path)):
            relative_path = Path(file_path).relative_to(self.workspace_path)
        else:
            logger.error(
                f"Unable to find file contents because somehow the file path {file_path} provided was not in the workspace path {self.workspace_path}"
            )
            return None

        if not _is_file_present_at_commit_hash(
            environment=self.environment, commit_hash=self.initial_tree_sha, relative_file_path=relative_path
        ):
            return None

        return _get_file_contents_at_commit_hash(
            environment=self.environment,
            commit_hash=self.initial_tree_sha,
            relative_file_path=relative_path,
        )

    def _get_file_snapshot(self, file_path: str) -> str | bytes | None:
        """Get the most recent snapshot of a file, falling back to git tree."""
        if file_path in self.file_snapshot_by_path:
            return self.file_snapshot_by_path[file_path]

        if self.initial_tree_sha:
            return self._get_file_from_git_tree(file_path)

        return None

    def _compute_diff_for_file_path(self, file_path: str) -> str | None:
        if not self.environment.exists(file_path):
            logger.debug("File {} does not exist, skipping diff", file_path)
            return None

        if not file_path.startswith(str(self.workspace_path)):
            logger.debug("File {} is outside workspace, skipping diff", file_path)
            return None

        try:
            old_content = self._get_file_snapshot(file_path)
            new_content = self.environment.read_file(file_path)

            logger.debug("Computing diff for {}", file_path)
            logger.trace("Old content: {}", old_content)
            logger.trace("New content: {}", new_content)

            diff = create_unified_diff(file_path, old_content, new_content)

            # TODO: I'm a little worried about having this cache and having it potentially leading to weird races
            # Update the snapshot with the new content for future diffs
            self.file_snapshot_by_path[file_path] = new_content
            logger.debug("Updated snapshot for {}", file_path)
            return diff
        except Exception as e:
            log_exception(
                e,
                f"Failed to compute diff for tool",
                priority=ExceptionPriority.LOW_PRIORITY,
                extra=dict(filepath=file_path),
            )
            return None

    def compute_diff_for_tool(self, tool_name: str, tool_input: ToolInput) -> str | None:
        """Compute diff between snapshot and current file state, then update snapshot."""
        if tool_name not in FILE_CHANGE_TOOL_NAMES:
            return None

        file_path = str(tool_input.get("file_path"))
        if not file_path:
            return None

        # claude emits absolute paths, so convert it to an environment-relative path
        return self._compute_diff_for_file_path(file_path=str(self.environment.to_environment_path(Path(file_path))))


def create_unified_diff(filepath: str, old_content: str | bytes | None, new_content: str | bytes) -> str | None:
    """
    Create a unified diff between old and new content using git diff.

    Handles:
    - File creation (old_content is None)
    - Both str and bytes content
    - Binary files

    Returns:
        Unified diff string or None if no changes
    """
    # Handle case where there's no change
    if old_content == new_content:
        return ""

    with tempfile.TemporaryDirectory() as old_dir, tempfile.TemporaryDirectory() as new_dir:
        # Use the same filename in both directories for proper diff
        temp_filename = generate_id()
        old_path = Path(old_dir) / temp_filename
        new_path = Path(new_dir) / temp_filename

        # Create parent directories
        old_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # Write old content (if exists)
        if old_content is not None:
            if isinstance(old_content, bytes):
                old_path.write_bytes(old_content)
            else:
                assert isinstance(old_content, str)
                old_path.write_text(old_content)

        # Write new content
        if isinstance(new_content, bytes):
            new_path.write_bytes(new_content)
        else:
            assert isinstance(new_content, str)
            new_path.write_text(new_content)

        try:
            # Use git diff to generate the diff
            # --no-index: compare files outside of git repo
            # --binary: handle binary files
            result = run_blocking(
                command=["git", "diff", "--no-index", "--binary", str(old_dir), str(new_dir)],
                is_checked=False,
                timeout=10.0,
            )

            # Return codes: 0 = no diff, 1 = diff found, other = error
            if result.returncode not in (0, 1):
                raise GitCommandFailure(
                    f"git diff returned unexpected code {result.returncode}: stdout={result.stdout}, stderr={result.stderr}",
                    command=["git", "diff", "--no-index", "--binary", str(old_dir), str(new_dir)],
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            diff = result.stdout

            # Clean up the temp directory paths from the diff
            # Git diff output uses different formats depending on the operation:
            # - For file creation: uses new path twice in diff --git line
            # - For file modification: uses old path then new path

            old_path_in_diff = f"{old_dir}/{temp_filename}"
            new_path_in_diff = f"{new_dir}/{temp_filename}"
            actual_path_with_leading_slash = filepath if filepath.startswith("/") else "/" + filepath

            # Handle the diff --git line
            # For file creation/deletion, git shows the same path twice
            if old_content is None:
                # File creation: git shows new path twice
                diff = diff.replace(
                    f"diff --git a{new_path_in_diff} b{new_path_in_diff}",
                    f"diff --git a{actual_path_with_leading_slash} b{actual_path_with_leading_slash}",
                )
            else:
                # File modification: git shows old then new
                diff = diff.replace(
                    f"diff --git a{old_path_in_diff} b{new_path_in_diff}",
                    f"diff --git a{actual_path_with_leading_slash} b{actual_path_with_leading_slash}",
                )

            # Handle --- and +++ lines
            # Since our temp paths are absolute (start with /), git concatenates directly without adding a slash
            # e.g., "a/var/folders/..." not "a//var/folders/..."
            diff = diff.replace(f"--- a{old_path_in_diff}", f"--- a{actual_path_with_leading_slash}")
            diff = diff.replace(f"+++ b{new_path_in_diff}", f"+++ b{actual_path_with_leading_slash}")

            # Special case: /dev/null remains unchanged (for file creation/deletion)

            # If empty diff, return None
            if not diff.strip():
                return None

            return diff
        except ProcessError as e:
            log_exception(
                e,
                f"Failed to compute diff for tool",
                priority=ExceptionPriority.LOW_PRIORITY,
                extra=dict(filepath=filepath),
            )
            return None
