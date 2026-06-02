import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.common import generate_id
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.state.chat_state import ToolInput
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.agents.default.constants import DEFAULT_WAIT_TIMEOUT
from sculptor.agents.default.constants import FILE_CHANGE_TOOL_NAMES
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.services.git_repo_service.git_errors import GitCommandFailure
from sculptor.tasks.handlers.run_agent.git import run_git_command_in_environment
from sculptor.utils.timeout import log_runtime_decorator


def _run_git_command_in_environment_and_handle_errors(
    environment: AgentExecutionEnvironment,
    command: list[str],
    error_message: str,
    extra: dict[str, Any] | None = None,
    timeout: float = 5.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str] | None:
    try:
        return run_git_command_in_environment(
            environment=environment,
            command=command,
            secrets=env,
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


def _is_file_present_at_commit_hash(
    environment: AgentExecutionEnvironment,
    commit_hash: str,
    relative_file_path: Path,
    env: dict[str, str] | None = None,
) -> bool:
    result = _run_git_command_in_environment_and_handle_errors(
        environment=environment,
        command=["git", "ls-tree", commit_hash, "--", str(relative_file_path)],
        error_message=f"Failed to check if {relative_file_path} was present at commit hash {commit_hash}",
        extra=dict(filepath=relative_file_path, initial_tree_sha=commit_hash),
        env=env,
    )

    if not result:
        return False

    returncode, stdout, _ = result
    return returncode == 0 and stdout.strip() != ""


def _get_file_contents_at_commit_hash(
    environment: AgentExecutionEnvironment,
    commit_hash: str,
    relative_file_path: Path,
    env: dict[str, str] | None = None,
) -> str | None:
    result = _run_git_command_in_environment_and_handle_errors(
        environment=environment,
        command=["git", "show", f"{commit_hash}:{relative_file_path}"],
        error_message=f"Failed to get file {relative_file_path} from git tree {commit_hash}",
        extra=dict(filepath=relative_file_path, initial_tree_sha=commit_hash),
        env=env,
    )

    if not result:
        return None

    _, stdout, _ = result
    return stdout


class DiffTracker:
    """Tracks file changes and computes diffs using in-memory snapshots."""

    def __init__(self, environment: AgentExecutionEnvironment) -> None:
        self.environment = environment
        self.code_directory = environment.get_working_directory()
        self.file_snapshot_by_path: dict[str, str | bytes | None] = {}
        # Stable temp directory for git objects written by _get_tree_hash.
        # Kept alive so tree SHAs remain resolvable for get_changed_file_paths()
        # at turn end. Cleaned up at the start of the next _get_tree_hash call.
        self._temp_objects_dir: Path | None = None
        self.initial_tree_sha = _get_tree_hash(self)

    def update_initial_tree_sha(self) -> None:
        """Update the initial git tree SHA and clear snapshots."""
        logger.info("Reinitializing diff tracker, getting new tree hash")
        initial_tree_sha = _get_tree_hash(self)
        self.initial_tree_sha = initial_tree_sha
        self.file_snapshot_by_path.clear()
        logger.debug("Updated initial_tree_sha to {}, cleared file snapshots", self.initial_tree_sha)

    def _get_alternate_objects_env(self) -> dict[str, str] | None:
        """Return env dict with GIT_ALTERNATE_OBJECT_DIRECTORIES if a temp objects dir exists."""
        if self._temp_objects_dir is None:
            return None
        return {"GIT_ALTERNATE_OBJECT_DIRECTORIES": str(self._temp_objects_dir)}

    def _get_file_from_git_tree(self, file_path: str) -> str | bytes | None:
        """Get file content from the initial git tree SHA."""
        if not self.initial_tree_sha:
            return None

        if file_path.startswith(str(self.code_directory)):
            relative_path = Path(file_path).relative_to(self.code_directory)
        else:
            logger.error(
                f"Unable to find file contents because somehow the file path {file_path} provided was not in the code directory {self.code_directory}"
            )
            return None

        env = self._get_alternate_objects_env()

        if not _is_file_present_at_commit_hash(
            environment=self.environment, commit_hash=self.initial_tree_sha, relative_file_path=relative_path, env=env
        ):
            return None

        return _get_file_contents_at_commit_hash(
            environment=self.environment,
            commit_hash=self.initial_tree_sha,
            relative_file_path=relative_path,
            env=env,
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

        if not file_path.startswith(str(self.code_directory)):
            logger.debug("File {} is outside code directory, skipping diff", file_path)
            return None

        try:
            old_content = self._get_file_snapshot(file_path)
            new_content = self.environment.read_file(file_path)

            logger.debug("Computing diff for {}", file_path)

            diff = create_unified_diff(file_path, old_content, new_content, self.environment.concurrency_group)

            # Update the snapshot with the new content for future diffs
            self.file_snapshot_by_path[file_path] = new_content
            logger.debug("Updated snapshot for {}", file_path)
            return diff
        except Exception as e:
            log_exception(
                e,
                "Failed to compute diff for tool",
                priority=ExceptionPriority.LOW_PRIORITY,
                extra=dict(filepath=file_path),
            )
            return None

    def to_git_relative_path(self, file_path: str) -> str:
        """Convert an absolute file path to a git-relative path.

        Strips the code_directory prefix so paths match what ``git diff`` produces.
        Paths outside the code directory are returned unchanged.
        """
        if not file_path:
            return file_path
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.code_directory / path

            # resolve() normalises macOS /var ↔ /private/var symlinks
            resolved_file = str(path.resolve())
            resolved_code_dir = str(self.code_directory.resolve())
            if not resolved_code_dir.endswith("/"):
                resolved_code_dir += "/"
            if resolved_file.startswith(resolved_code_dir):
                return resolved_file[len(resolved_code_dir) :]
        except Exception:
            pass
        return file_path

    def compute_diff_for_tool(self, tool_name: str, tool_input: ToolInput) -> str | None:
        """Compute diff between snapshot and current file state, then update snapshot."""
        if tool_name not in FILE_CHANGE_TOOL_NAMES:
            return None

        file_path = str(tool_input.get("file_path"))
        if not file_path:
            return None

        # Claude typically emits absolute paths, but handle relative paths
        # gracefully by resolving them against the code directory.
        path = Path(file_path)
        if not path.is_absolute():
            path = self.code_directory / path

        return self._compute_diff_for_file_path(file_path=str(self.environment.to_environment_path(path)))

    def get_changed_file_paths(self) -> list[str]:
        """Get list of files changed since the initial tree SHA.

        Computes a diff between the tree SHA captured at turn start and the
        current working tree state (including untracked files). This catches
        ALL file changes regardless of which tool made them (Edit, Write, Bash, etc.).

        Returns git-relative file paths. Returns an empty list on any error.
        """
        if not self.initial_tree_sha:
            return []

        try:
            current_tree_sha = _get_tree_hash(self)
            if not current_tree_sha:
                return []

            if self.initial_tree_sha == current_tree_sha:
                return []

            # Both tree SHAs may reference objects in the temp directory,
            # so we need GIT_ALTERNATE_OBJECT_DIRECTORIES for git diff-tree.
            env = self._get_alternate_objects_env()

            result = _run_git_command_in_environment_and_handle_errors(
                environment=self.environment,
                command=[
                    "git",
                    "diff-tree",
                    "-r",
                    "--name-only",
                    "--no-commit-id",
                    self.initial_tree_sha,
                    current_tree_sha,
                ],
                error_message="Failed to diff trees for changed file paths",
                extra=dict(initial_tree_sha=self.initial_tree_sha, current_tree_sha=current_tree_sha),
                timeout=10.0,
                env=env,
            )
            if not result:
                return []

            _, stdout, _ = result
            return [line for line in stdout.strip().split("\n") if line]
        except Exception as e:
            log_exception(
                e,
                "Failed to get changed file paths",
                priority=ExceptionPriority.LOW_PRIORITY,
            )
            return []


def create_unified_diff(
    filepath: str, old_content: str | bytes | None, new_content: str | bytes, concurrency_group: ConcurrencyGroup
) -> str | None:
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
            result = concurrency_group.run_process_to_completion(
                command=["git", "diff", "--no-index", "--binary", str(old_dir), str(new_dir)],
                is_checked_after=False,
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
            # TODO: This does not handle filenames with special characters. See
            #   https://git-scm.com/docs/git-config#Documentation/git-config.txt-corequotePath
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
                "Failed to compute diff for tool",
                priority=ExceptionPriority.LOW_PRIORITY,
                extra=dict(filepath=filepath),
            )
            return None


def _resolve_git_path(environment: AgentExecutionEnvironment, rev_parse_flag: str) -> str:
    """Resolve a git path like ``--git-dir`` or ``--git-common-dir`` in the agent's working dir.

    Returned as an absolute path so it stays valid regardless of subprocess cwd.
    Worktrees have a `.git` *file* pointing at the per-worktree dir; the common
    dir holds the shared `objects/` store. Hardcoding `.git/...` only works in
    non-worktree repos.
    """
    _, stdout, _ = run_git_command_in_environment(
        environment,
        ["git", "rev-parse", rev_parse_flag],
        {},
        check_output=True,
        timeout=DEFAULT_WAIT_TIMEOUT,
    )
    path = Path(stdout.strip())
    if not path.is_absolute():
        path = environment.get_working_directory() / path
    return str(path)


def _get_tree_hash(diff_tracker: DiffTracker) -> str | None:
    """Get a tree SHA representing the current working tree state.

    Objects are written to a stable temp directory owned by the DiffTracker,
    so tree SHAs remain resolvable for later git diff-tree calls.
    """
    try:
        if _has_untracked_or_unstaged_changes(diff_tracker.environment):
            return _get_tree_hash_with_untracked_and_unstaged_changes(diff_tracker)
        else:
            return _get_tree_hash_from_staged_changes(diff_tracker.environment)
    except Exception as e:
        log_exception(
            e,
            "Failed to get git tree SHA",
            priority=ExceptionPriority.LOW_PRIORITY,
        )
        return None


def _has_untracked_or_unstaged_changes(environment: AgentExecutionEnvironment) -> bool:
    _, stdout, _ = run_git_command_in_environment(environment, ["git", "status", "--porcelain"], {}, check_output=True)
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        # Check for unstaged (2nd char not space) or untracked (??)
        if line[1] != " " or line.startswith("??"):
            return True
    return False


def _get_tree_hash_from_staged_changes(environment: AgentExecutionEnvironment) -> str | None:
    # Fast path: just use current index (staged changes only)
    _, stdout, _ = run_git_command_in_environment(
        environment,
        ["git", "write-tree"],
        {},
        check_output=True,
        timeout=DEFAULT_WAIT_TIMEOUT,
        is_retry_safe=False,
    )
    tree_sha = stdout.strip()
    logger.debug("Created tree SHA from current index (staged changes only): {}", tree_sha)
    return tree_sha


@log_runtime_decorator()
def _get_tree_hash_with_untracked_and_unstaged_changes(diff_tracker: DiffTracker) -> str | None:
    environment = diff_tracker.environment

    # Clean up the previous temp objects directory if one exists.
    # The old tree SHAs are no longer needed once we're computing a new snapshot.
    prev_temp_dir = diff_tracker._temp_objects_dir
    if prev_temp_dir is not None:
        diff_tracker._temp_objects_dir = None
        environment.run_process_in_background(["rm", "-rf", str(prev_temp_dir.parent)], {}).wait(
            timeout=DEFAULT_WAIT_TIMEOUT
        )

    # Slow path: include untracked and unstaged changes.
    # Use a temporary index (to avoid mutating the real index) and a temporary
    # objects directory (to avoid polluting the real git objects dir). The temp
    # objects dir is kept alive on the DiffTracker so tree SHAs remain resolvable
    # for get_changed_file_paths() at turn end.
    #
    # Resolve the real git paths via git rev-parse instead of hardcoding
    # `.git/index` / `.git/objects`. In a worktree checkout `.git` is a gitfile
    # pointer (regular file), so those literal paths do not exist:
    #   - --git-dir points to the per-worktree git directory, which owns `index`
    #   - --git-common-dir points to the shared git directory, which owns `objects`
    git_dir = _resolve_git_path(environment, "--git-dir")
    git_common_dir = _resolve_git_path(environment, "--git-common-dir")

    temp_git_dir = environment.get_root_path() / f".git_{generate_id()}"
    temp_index = temp_git_dir / "index"
    temp_objects = temp_git_dir / "objects"
    try:
        environment.run_process_to_completion(["mkdir", "-p", str(temp_objects)], {})

        env: dict[str, str] = {
            "GIT_INDEX_FILE": str(temp_index),
            "GIT_OBJECT_DIRECTORY": str(temp_objects),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(Path(git_common_dir) / "objects"),
        }

        # Copy the current index to temp index, preserving mtime.
        # If the mtime differs from the real index, git will do internal bookkeeping
        # that updates packfile mtimes, which can cause large snapshot size increases.
        # Using cp -p preserves the modification time cross-platform (Linux and macOS).
        environment.run_process_to_completion(["cp", "-p", str(Path(git_dir) / "index"), str(temp_index)], {})

        # Add all files (including untracked) to the temp index
        run_git_command_in_environment(environment, ["git", "add", "-A"], env, check_output=True)

        # Write tree from temp index
        _, stdout, _ = run_git_command_in_environment(
            environment,
            ["git", "write-tree"],
            env,
            check_output=True,
            timeout=DEFAULT_WAIT_TIMEOUT,
            is_retry_safe=False,
        )

        tree_sha = stdout.strip()
        logger.debug("Created tree SHA including all changes: {}", tree_sha)

        # Keep the temp objects dir alive so the tree SHA remains resolvable.
        # The temp index is no longer needed — only the objects matter.
        diff_tracker._temp_objects_dir = temp_objects
        environment.run_process_in_background(["rm", "-f", str(temp_index)], {}).wait(timeout=DEFAULT_WAIT_TIMEOUT)

        return tree_sha
    except Exception:
        # On failure, clean up everything
        environment.run_process_in_background(["rm", "-rf", str(temp_git_dir)], {}).wait(timeout=DEFAULT_WAIT_TIMEOUT)
        raise
