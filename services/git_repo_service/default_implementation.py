import time
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
from threading import Lock
from typing import Final
from typing import Generator
from typing import TypeVar

import pathspec
from loguru import logger
from pydantic import AnyUrl
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import run_blocking
from imbue_core.subprocess_utils import ProcessError
from imbue_core.subprocess_utils import ProcessSetupError
from sculptor.database.models import Project
from sculptor.database.models import TaskID
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.constants import ENVIRONMENT_WORKSPACE_DIRECTORY
from sculptor.primitives.ids import UserReference
from sculptor.services.git_repo_service.api import AbsoluteGitReference
from sculptor.services.git_repo_service.api import GitRepoFileStatus
from sculptor.services.git_repo_service.api import GitRepoMergeResult
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.api import GitRepoStatus
from sculptor.services.git_repo_service.api import ReadOnlyGitRepo
from sculptor.services.git_repo_service.api import WritableGitRepo
from sculptor.services.git_repo_service.api import is_git_merge_result_up_to_date
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.tasks.handlers.run_agent.errors import GitCommandFailure
from sculptor.tasks.handlers.run_agent.git import run_git_command_in_environment
from sculptor.tasks.handlers.run_agent.git import run_git_command_local
from sculptor.utils.timeout import log_runtime_decorator

T = TypeVar("T")

NULL_DELIMITER_FOR_FOOLPROOF_PARSING: Final = "\x00"


class _ReadOnlyGitRepoSharedMethods(ReadOnlyGitRepo, ABC):
    @abstractmethod
    def get_repo_url(self) -> AnyUrl:
        """Get a reference to the git repository."""
        ...

    @abstractmethod
    def _run_git(self, args: list[str]) -> str: ...

    @abstractmethod
    def read_file(self, repo_relative_path: Path) -> str | None: ...

    @abstractmethod
    def does_relative_file_exist(self, repo_relative_path: Path) -> bool: ...

    @cached_property
    def is_bare_repo(self) -> bool:
        return self._run_git(["rev-parse", "--is-bare-repository"]).strip() == "true"

    @property
    def _git_dir_relpath(self) -> Path:
        return Path(".") if self.is_bare_repo else Path(".git")

    def is_branch_ref(self, branch: str) -> bool:
        try:
            self._run_git(
                ["rev-parse", "--verify", f"refs/heads/{branch}"],
            )
            return True
        except GitRepoError:
            return False

    def get_current_commit_hash(self) -> str:
        return self._run_git(["rev-parse", "HEAD"]).strip()

    def get_branch_head_commit_hash(self, branch_name: str) -> str:
        "will raise GitRepoError if branch doesn't exist"
        return self._run_git(["rev-parse", branch_name]).strip()

    def get_current_git_branch(self) -> str:
        """Get the current git branch name for a repository."""
        logger.trace("Getting current branch...")
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        logger.trace("Current branch: {}", branch)
        return branch

    def get_num_uncommitted_changes(self) -> int:
        return len(self._run_git(["status", "--porcelain"]).strip().splitlines())

    def get_absolute_reference_to_current_location(self) -> AbsoluteGitReference:
        return AbsoluteGitReference(
            repo_url=self.get_repo_url(),
            branch=self.get_current_git_branch(),
            commit_hash=self.get_current_commit_hash(),
        )

    def list_matching_folders(self, pattern: str = "") -> list[str]:
        """List all folders in the repository."""
        logger.info("Listing all folders in the repository...")
        result = self._run_git(["ls-tree", "-d", "--name-only", "-r", "-z", "HEAD"])
        folders = [f.strip() for f in result.split("\0")[:-1] if f.strip()]
        return [(f + "/") for f in folders if pattern.lower() in f.lower()]

    def list_matching_files(self, pattern: str | None = "") -> list[str]:
        """List all files in the repository."""
        logger.info("Listing all files in the repository...")
        result = self._run_git(["ls-files", "-z"])
        files = [f.strip() for f in result.split("\0")[:-1] if f.strip()]
        if not pattern:
            return files
        return [f for f in files if pattern.lower() in f.lower()]

    def list_untracked_files(self) -> list[str]:
        """List all untracked files in the repository, including .gitignored files."""
        logger.info("Checking for untracked files (including .gitignored)...")
        result = self._run_git(["ls-files", "--others", "--exclude-standard", "-z"])
        return [f.strip() for f in result.split("\0")[:-1] if f.strip()]

    def _list_diff_files(self, is_staged: bool, diff_filter: str | None = None) -> list[str]:
        cmd = ["diff", "--name-only"]
        if is_staged:
            cmd.append("--cached")
        if diff_filter:
            cmd.append(f"--diff-filter={diff_filter}")
        result = self._run_git(cmd)
        return [f.strip() for f in result.split("\n") if f.strip()]

    # TODO(mjr): consider if this helper really belong here? also bare diff filter feels awkward
    def list_staged(self, diff_filter: str | None = None) -> list[str]:
        return self._list_diff_files(is_staged=True, diff_filter=diff_filter)

    def list_unstaged(self, diff_filter: str | None = None) -> list[str]:
        return self._list_diff_files(is_staged=False, diff_filter=diff_filter)

    # NOTE: A little goofy that a read-only repo can push a write to a different repo but seems fine
    def push_ref_to_remote(self, remote: str, local_ref: str, remote_ref: str, is_forced: bool = False) -> str:
        _validate_ref_normalcy(remote_ref)
        _validate_ref_normalcy(local_ref)
        args = [
            "push",
            "--no-verify",  # disable pre-push hook
        ]
        if is_forced:
            args.append("--force")

        args.extend(
            [
                remote,
                f"{local_ref}:{remote_ref}",
            ]
        )
        return self._run_git(args)

    @log_runtime_decorator("get_recent_branches")
    def get_recent_branches(self) -> list[str]:
        # Get recent branches using git reflog
        reflog_result = self._run_git(["reflog", "--format=%gs"])

        # Parse reflog to find branch checkouts
        branches = []
        seen_values: set[str] = set()
        start_time = time.monotonic()
        for line in reflog_result.strip().split("\n"):
            if "checkout: moving from" in line:
                # Extract the target branch from the reflog entry
                parts = line.split(" to ")
                if len(parts) == 2:
                    branch = parts[1].strip()
                    if branch and branch not in seen_values:
                        seen_values.add(branch)
                        if self.is_branch_ref(branch):
                            # if it is really a branch and not a commit hash, add it to the list
                            branches.append(branch)
                            if len(branches) >= 5:
                                return branches
            if time.monotonic() - start_time > 3.0:
                logger.debug(
                    "getting most recent branches is taking too long - backing off to the default of only getting the current branch"
                )
                break
        if len(branches) == 0:
            # fallback to looking for the current branch in the case that the user has fresh state (ex. pruned recently)
            current = self.get_current_git_branch()
            return [current] if current and current != "HEAD" else []
        return branches

    # TODO: Hopefully we never run these over ssh
    @property
    def is_merge_in_progress(self) -> bool:
        return self.does_relative_file_exist(self._git_dir_relpath / "MERGE_HEAD")

    @property
    def is_rebase_in_progress(self) -> bool:
        if self.does_relative_file_exist(self._git_dir_relpath / "rebase-merge"):
            return True
        return self.does_relative_file_exist(self._git_dir_relpath / "rebase-apply")

    @property
    def is_cherry_pick_in_progress(self) -> bool:
        return self.does_relative_file_exist(self._git_dir_relpath / "CHERRY_PICK_HEAD")

    def get_current_status(
        self, is_read_only_and_lockless: bool = False, additional_ignores: tuple[str, ...] | None = None
    ) -> GitRepoStatus:
        """Get the current status of the git repository."""
        # NOTE: --no-renames is used to simplify parsing, otherwise renames produce two lines per operation with -z
        args = ["status", "--porcelain=v1", "-z", "--no-renames", "--ignored=traditional", "--untracked-files=all"]

        if is_read_only_and_lockless:
            args = ["--no-optional-locks", *args]
        status_output = self._run_git(args)

        repo_file_status = _parse_git_status_file_counts(
            status_output, delimiter=NULL_DELIMITER_FOR_FOOLPROOF_PARSING, additional_ignores=additional_ignores
        )
        return GitRepoStatus(
            files=repo_file_status,
            is_merging=self.is_merge_in_progress,
            is_rebasing=self.is_rebase_in_progress,
            is_cherry_picking=self.is_cherry_pick_in_progress,
        )


class LocalReadOnlyGitRepo(_ReadOnlyGitRepoSharedMethods):
    repo_path: Path

    def get_repo_path(self) -> Path:
        """Get the path to the git repository."""
        return self.repo_path

    def get_repo_url(self) -> AnyUrl:
        return AnyUrl(f"file://{self.repo_path}")

    @cached_property
    def is_bare_repo(self) -> bool:
        return self._run_git(["rev-parse", "--is-bare-repository"]).strip() == "true"

    def export_current_repo_state(self, target_folder: Path) -> None:
        current_user_repo_path = self.repo_path
        # we are copying everything from .git *except* the objects folder, which can be very large
        # and we are copying all files that have changed (staged and unstaged) plus untracked files
        command = [
            "bash",
            "-c",
            "{ git status --porcelain | grep -E '^\\?\\?|^.M|^M' | cut -c4- ; echo '.git' ; } | rsync -av --exclude='.git/objects/' --files-from=- '"
            + str(current_user_repo_path).rstrip("/")
            + "/' '"
            + str(target_folder).rstrip("/")
            + "/'",
        ]
        run_blocking(command, cwd=current_user_repo_path)

    def _run_git(self, args: list[str]) -> str:
        """Run a git command in the specified repository."""
        try:
            cmd_to_run = ["git"] + args
            _, result_stdout, _ = run_git_command_local(cmd_to_run, self.repo_path, is_retry_safe=False)
            return result_stdout
        except FileNotFoundError:
            raise
        except (GitCommandFailure, ProcessError) as e:
            try:
                cmd_to_run = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
                _, result_stdout, _ = run_git_command_local(cmd_to_run, self.repo_path, is_retry_safe=False)
                branch_name = result_stdout.strip()
            except Exception as e2:
                if isinstance(e2, FileNotFoundError):
                    raise
                if isinstance(e2, ProcessSetupError) and not self.repo_path.exists():
                    raise FileNotFoundError(f"Repository path does not exist: {self.repo_path}") from e
                if isinstance(e2, ProcessError) and "unknown revision or path not in the working tree" in e.stderr:
                    logger.debug("Repository appears to be empty, no commits yet")
                    branch_name = None
                else:
                    log_exception(e2, "Failed to get current branch name for error reporting")
                    branch_name = "unknown"
            raise GitRepoError(
                message="Git command failed",
                operation=" ".join(args),
                branch_name=branch_name,
                repo_url=self.get_repo_url(),
                exit_code=getattr(e, "returncode", -1),
                stderr=e.stderr,
            ) from e

    def read_file(self, repo_relative_path: Path) -> str | None:
        try:
            file_path = self.repo_path / repo_relative_path
            if not file_path.exists():
                return None
            with file_path.open("r", encoding="utf-8") as f:
                return f.read()
        except (OSError, FileNotFoundError) as e:
            logger.trace("Failed to read file {}: {}", repo_relative_path, e)
            return None
        except Exception as e:
            log_exception(e, "Failed to read file from git repository", priority=ExceptionPriority.LOW_PRIORITY)
            return None

    def does_relative_file_exist(self, repo_relative_path: Path) -> bool:
        return (self.repo_path / repo_relative_path).exists()


class RemoteReadOnlyGitRepo(_ReadOnlyGitRepoSharedMethods):
    environment: Environment

    def get_repo_url(self) -> AnyUrl:
        return self.environment.get_repo_url()

    def get_repo_path(self) -> Path:
        msg = "RemoteReadOnlyGitRepo does not have a local path. Leaving it in the base class for legacy reasons."
        raise NotImplementedError(msg)

    def get_internal_environment_path_str(self, repo_relative_path: Path) -> str:
        return f"{self.environment.get_workspace_path()}/{repo_relative_path.as_posix()}"

    def export_current_repo_state(self, target_folder: Path) -> None:
        raise NotImplementedError("No need to support this yet")

    def read_file(self, repo_relative_path: Path) -> str | None:
        try:
            content = self.environment.read_file(self.get_internal_environment_path_str(repo_relative_path))
            assert isinstance(content, str), "this shouldn't be called much but should definitely be text if it is"
            return content
        except FileNotFoundError as e:
            logger.trace("Failed to read file {}: {}", repo_relative_path, e)
            return None

    def does_relative_file_exist(self, repo_relative_path: Path) -> bool:
        try:
            return self.environment.exists(self.get_internal_environment_path_str(repo_relative_path))
        except FileNotFoundError as e:
            logger.trace("Failed to read file {}: {}", repo_relative_path, e)
            return False

    def _run_git(self, args: list[str]) -> str:
        """Run a git command in the specified repository."""
        try:
            cmd_to_run = ["git"] + args
            _, result_stdout, _ = run_git_command_in_environment(
                self.environment, cmd_to_run, secrets={}, cwd=str(ENVIRONMENT_WORKSPACE_DIRECTORY), is_retry_safe=False
            )
            return result_stdout
        except FileNotFoundError:
            raise
        except (GitCommandFailure, ProcessError) as e:
            try:
                cmd_to_run = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
                _, result_stdout, _ = run_git_command_in_environment(
                    self.environment,
                    cmd_to_run,
                    secrets={},
                    is_retry_safe=False,
                    cwd=str(ENVIRONMENT_WORKSPACE_DIRECTORY),
                )
                branch_name = result_stdout.strip()
            except Exception as e2:
                if isinstance(e2, FileNotFoundError):
                    raise
                if isinstance(e2, ProcessError) and "unknown revision or path not in the working tree" in e.stderr:
                    logger.debug("Repository appears to be empty, no commits yet")
                    branch_name = None
                else:
                    log_exception(e2, "Failed to get current branch name for error reporting")
                    branch_name = "unknown"
            raise GitRepoError(
                message="Git command failed",
                operation=" ".join(args),
                branch_name=branch_name,
                repo_url=self.get_repo_url(),
                exit_code=getattr(e, "returncode", -1),
                stderr=e.stderr,
            ) from e


def _parse_git_status_file_counts(
    status_output: str, delimiter: str, additional_ignores: tuple[str, ...] | None = None
) -> GitRepoFileStatus:
    """
    Parses the output of git status. Expects it to be a list
    of delimiter-separated entries. One entry per file.

    Returns a summarized counts of changed files treating any untracked files
    matching the additional_ignores as regularly ignored files.

    Each entry in the result describes a single file (newlines in paths
    are escaped by `git`). Each entry opens with two characters (XY below)
    and is followed by a filename or two (for renames).

    Excerpt from `git-status` manual page, the first section describes the
    results if a no merge is in progress or merge is resolved, the second
    section indicates the details of a merge that is in progress, untracked
    and ignored files are shows independently of the two states.

        X          Y     Meaning
        -------------------------------------------------
                 [AMD]   not updated
        M        [ MTD]  updated in index
        T        [ MTD]  type changed in index
        A        [ MTD]  added to index
        D                deleted from index
        R        [ MTD]  renamed in index
        C        [ MTD]  copied in index
        [MTARC]          index and work tree matches
        [ MTARC]    M    work tree changed since index
        [ MTARC]    T    type changed in work tree since index
        [ MTARC]    D    deleted in work tree
                    R    renamed in work tree
                    C    copied in work tree
        -------------------------------------------------
        D           D    unmerged, both deleted
        A           U    unmerged, added by us
        U           D    unmerged, deleted by them
        U           A    unmerged, added by them
        D           U    unmerged, deleted by us
        A           A    unmerged, both added
        U           U    unmerged, both modified
        -------------------------------------------------
        ?           ?    untracked
        !           !    ignored
        -------------------------------------------------
    """

    unstaged_files = 0
    staged_files = 0
    untracked_files = 0
    deleted_files = 0
    ignored_files = 0

    ignore_spec = None
    if additional_ignores:
        ignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", additional_ignores)

    for line in status_output.split(delimiter):
        if not line:
            continue

        # Porcelain format: XY filename
        # X = staged status, Y = unstaged status
        if len(line) < 2:
            continue
        staged_status = line[0]
        unstaged_status = line[1]

        # Count total deleted files (can be staged or unstaged)
        if staged_status == "D" or unstaged_status == "D":
            deleted_files += 1
        # Count total unstaged changes
        if unstaged_status != " " and unstaged_status != "?" and unstaged_status != "!":
            unstaged_files += 1

        # Untracked files will have both flags set to '?'
        if staged_status == "?" or unstaged_status == "?":
            if ignore_spec and ignore_spec.match_file(line[3:]):
                ignored_files += 1
                continue
            untracked_files += 1
        # Ignored files will have both flags set to '!'
        elif staged_status == "!" or unstaged_status == "!":
            ignored_files += 1
        # Count staged changes, their nature does not matter
        elif staged_status != " ":
            staged_files += 1

    return GitRepoFileStatus(
        unstaged=unstaged_files,
        staged=staged_files,
        untracked=untracked_files,
        deleted=deleted_files,
        ignored=ignored_files,
    )


class _WritableGitRepoSharedMethods(WritableGitRepo, ABC):
    @abstractmethod
    def _run_git(self, args: list[str]) -> str: ...

    def maybe_fetch_remote_branch_into_local(
        self,
        local_branch: str,
        remote: AnyUrl,
        remote_branch: str,
        dry_run: bool = False,
        force: bool = False,
        dangerously_update_head_ok: bool = False,
    ) -> bool:
        logger.debug(
            "Attempting to fetch the branch {} from {} onto {} (force={}, dry-run={}, update-head-ok={})",
            remote_branch,
            remote,
            local_branch,
            force,
            dry_run,
            dangerously_update_head_ok,
        )
        # NOTE: we can't use --porcelain, it's too new
        #       this means the result is on stderr and not stdout
        #       and that it includes other garbage in the output
        args = ["fetch", str(remote), f"refs/heads/{remote_branch}:refs/heads/{local_branch}", "--show-forced-updates"]
        if dry_run:
            args.append("--dry-run")
        if force:
            args.append("--force")
        if dangerously_update_head_ok:
            args.append("--update-head-ok")

        try:
            self._run_git(args)
            logger.debug("Git fetch successful ({})", " ".join(args))
            return True
        except GitRepoError as e:
            logger.debug("Fetch failed with exit code {}; {} (full command: {})", e.exit_code, str(e), " ".join(args))
            if e.exit_code == 1:
                # FIXME: parse the stderr to confirm that we got a rejection and not bad refs or similar
                return False
            # likely 128 and an unexpected error
            raise

    def merge_from_ref(self, ref: str, commit_message: str | None = None) -> GitRepoMergeResult:
        """Merge the given ref into current checkout.

        Does not re-raise any git operation errors.
        """
        logger.debug("Merging from ref {} onto local branch (message={})", ref, commit_message)
        # FIXME: would want to have --no-autostash but that's not something that all git versions support
        args = ["merge", "--commit", "--ff", "--no-edit", "--stat"]
        if commit_message:
            args.extend(["-m", commit_message])

        args.append(ref)
        try:
            merge_output = self._run_git(args)
            return GitRepoMergeResult(
                is_merged=True,
                raw_output=merge_output,
                was_up_to_date=is_git_merge_result_up_to_date(merge_output),
            )
        except GitRepoError as e:
            if self.is_merge_in_progress:
                return GitRepoMergeResult(
                    is_merged=False,
                    raw_output=str(e.stderr),
                )
            # FIXME: we could actually parse the output and identify some of these
            #        and return a more meaningful result from this
            # As one example, "Please commit your changes or stash them before you merge".
            return GitRepoMergeResult(
                is_merged=False,
                raw_output=str(e.stderr),
            )

    def pull_from_remote(
        self,
        remote: str,
        remote_branch: str,
        should_abort_on_conflict: bool = False,
        is_fast_forward_only: bool = False,
        assert_local_branch_equals_to: str | None = None,
    ) -> GitRepoMergeResult:
        # TODO: consider auto-stashing as an option
        logger.debug(
            "Pulling a remote branch {} from {} onto local branch (should_abort_on_conflict={}, is_fast_forward_only={}, assert_local_branch_equals_to={})",
            remote_branch,
            remote,
            should_abort_on_conflict,
            is_fast_forward_only,
            assert_local_branch_equals_to,
        )

        args = [
            "pull",
            remote,
            f"refs/heads/{remote_branch}",
            "--no-rebase",
        ]
        if is_fast_forward_only:
            args.append("--ff-only")

        try:
            merge_output = self._run_git(args)
            logger.debug("Git pull successful ({}). Output: {}", " ".join(args), merge_output)

            return GitRepoMergeResult(
                is_merged=True,
                raw_output=merge_output,
                was_up_to_date=is_git_merge_result_up_to_date(merge_output),
            )
        except GitRepoError as e:
            stderr = str(e.stderr)
            is_simple_fast_forward_failure = (
                is_fast_forward_only
                and e.exit_code == 128
                and any(line.startswith("fatal: Not possible to fast-forward") for line in stderr.splitlines())
            )
            if is_simple_fast_forward_failure:
                return GitRepoMergeResult(
                    is_merged=False,
                    raw_output=stderr,
                )
            # "error: Your local changes to the following files would be overwritten by merge"
            # "error: The following untracked working tree files would be overwritten"
            if any(
                (line.startswith("error:") and "files would be overwritten" in line) for line in stderr.splitlines()
            ):
                return GitRepoMergeResult(
                    is_merged=False,
                    is_stopped_by_uncommitted_changes=True,
                    raw_output=stderr,
                )

            # re-raise if the non-fast forward caused a problem but did not result in an unresolved merge state
            if not (not is_fast_forward_only and self.is_merge_in_progress):
                raise

            if not (self.is_merge_in_progress and should_abort_on_conflict):
                # unknown state but it clearly failed
                return GitRepoMergeResult(
                    is_merged=False,
                    is_aborted=False,
                    raw_output=stderr,
                )

            logger.debug("Attempting to abort the merge operation")
            # TODO: handle `git merge --abort` failing?
            abort_output = self._run_git(["merge", "--abort"])
            return GitRepoMergeResult(is_merged=False, is_aborted=True, raw_output="\n\n".join((stderr, abort_output)))

    def ensure_local_branch_has_remote_branch_ref(self, remote_repo: AnyUrl, remote_branch: str) -> bool:
        return self.is_branch_ref(remote_branch) or self.maybe_fetch_remote_branch_into_local(
            local_branch=remote_branch, remote=remote_repo, remote_branch=remote_branch
        )

    def create_git_stash(self, stash_message: str) -> bool:
        """Create a git stash and return whether any changes were stashed."""
        logger.debug("Stashing tracked changes...")
        # TODO: Blanket string escaping. Still not entirely sure why we don't use GitPython
        result = self._run_git(["stash", "push", "-m", f"'{stash_message}'"])
        has_stash = "No local changes" not in result
        logger.info("Stash result - Has stash: {}", has_stash)
        return has_stash

    def git_checkout_branch(self, branch_name: str) -> None:
        """Checkout a git branch."""
        logger.debug("Checking out task branch: {}", branch_name)
        self._run_git(["checkout", branch_name])

    def reset_working_directory(self) -> None:
        """Reset working directory to clean state."""
        logger.debug("Cleaning up uncommitted changes...")
        self._run_git(["reset", "--hard", "HEAD"])
        logger.info("Reset staged/modified files")

        self._run_git(["clean", "-fd"])
        logger.debug("Removed untracked files and directories")

    def restore_git_stash(self, stash_message: str) -> None:
        """Restore a specific git stash by finding it using the unique message."""
        logger.debug("Restoring stashed changes with message: {}", stash_message)

        stash_list = self._run_git(["stash", "list"]).strip()
        if not stash_list:
            raise GitRepoError(
                f"No stashes found: cannot restore stash with message '{stash_message}'",
                operation="stash_pop",
                repo_url=self.get_repo_url(),
                exit_code=None,
                stderr="No stashes exist",
            )

        stash_index = None
        for line in stash_list.splitlines():
            # Format: stash@{N}: On branch_name: message
            if stash_message in line:
                # Extract stash@{N} from the beginning of the line
                stash_ref = line.split(":")[0]
                stash_index = stash_ref
                break

        if stash_index is None:
            raise GitRepoError(
                f"Could not find stash with message '{stash_message}'",
                operation="stash_pop",
                repo_url=self.get_repo_url(),
                exit_code=None,
                stderr=f"Available stashes:\n{stash_list}",
            )

        logger.debug("Found stash to restore: {}", stash_index)
        self._run_git(["stash", "pop", stash_index])


class LocalWritableGitRepo(LocalReadOnlyGitRepo, _WritableGitRepoSharedMethods):
    pass


class RemoteWritableGitRepo(RemoteReadOnlyGitRepo, _WritableGitRepoSharedMethods):
    pass


class DefaultGitRepoService(GitRepoService):
    """Default implementation of GitRepoService using direct git commands in an Environment."""

    _lock_lock: Lock = PrivateAttr(default_factory=Lock)
    _local_lock_by_project_id: dict[ProjectID, Lock] = PrivateAttr(default_factory=dict)
    _agent_lock_by_task_id: dict[TaskID, Lock] = PrivateAttr(default_factory=dict)

    def _get_lock(self, key: T, lock_map: dict[T, Lock]) -> Lock:
        with self._lock_lock:
            if lock_map.get(key) is None:
                lock_map[key] = Lock()
        return lock_map[key]

    def _get_local_project_lock(self, project_id: ProjectID) -> Lock:
        """Get a lock for the local project to ensure thread-safe access."""
        return self._get_lock(project_id, self._local_lock_by_project_id)

    def _get_agent_task_lock(self, task_id: TaskID) -> Lock:
        """Get a lock for the agent repo to ensure thread-safe access."""
        return self._get_lock(task_id, self._agent_lock_by_task_id)

    def _get_repo_path(self, project: Project) -> Path:
        user_git_repo_url = project.user_git_repo_url
        assert user_git_repo_url is not None and user_git_repo_url.startswith("file://"), (
            "Only local git repositories are supported"
        )
        return Path(user_git_repo_url.replace("file://", ""))

    @contextmanager
    def open_local_user_git_repo_for_read(
        self, user_reference: UserReference, project: Project
    ) -> Generator[LocalReadOnlyGitRepo, None, None]:
        with self._get_local_project_lock(project.object_id):
            repo_path = self._get_repo_path(project)
            yield LocalReadOnlyGitRepo(repo_path=repo_path)

    @contextmanager
    def open_local_user_git_repo_for_write(
        self, user_reference: UserReference, project: Project
    ) -> Generator[LocalWritableGitRepo, None, None]:
        with self._get_local_project_lock(project.object_id):
            repo_path = self._get_repo_path(project)
            yield LocalWritableGitRepo(repo_path=repo_path)

    @contextmanager
    def open_remote_agent_git_repo_for_read(
        self, task_id: TaskID, environment: Environment
    ) -> Generator[RemoteReadOnlyGitRepo, None, None]:
        with self._get_agent_task_lock(task_id):
            yield RemoteReadOnlyGitRepo(environment=environment)


def _validate_ref_normalcy(git_ref: str):
    """Validates the the ref can be used directly as a parameter, does not include special characters, and does not start with special +"""
    git_ref = git_ref.strip()
    assert git_ref and (":" not in git_ref) and not git_ref.startswith("+")
