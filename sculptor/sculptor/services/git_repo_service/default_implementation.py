from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from loguru import logger
from pydantic import AnyUrl

from sculptor.database.models import Project
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.subprocess_utils import ProcessError
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.git_repo_service.error_types import GitRepoNotFoundError
from sculptor.services.git_repo_service.git_commands import run_git_command_local
from sculptor.services.git_repo_service.git_errors import GitCommandFailure
from sculptor.services.git_repo_service.git_repos import ReadOnlyGitRepo
from sculptor.services.git_repo_service.git_repos import WritableGitRepo
from sculptor.utils.timeout import log_runtime_decorator


class _GitRepoSharedMethods(ReadOnlyGitRepo, ABC):
    @abstractmethod
    def _run_git(self, args: list[str]) -> str: ...


class _ReadOnlyGitRepoSharedMethods(_GitRepoSharedMethods, ABC):
    @abstractmethod
    def get_repo_url(self) -> AnyUrl:
        """Get a reference to the git repository."""
        ...

    def is_branch_ref(self, branch: str) -> bool:
        try:
            self._run_git(["rev-parse", "--verify", f"refs/heads/{branch}"])
            return True
        except GitRepoError:
            return False

    def is_valid_branch_name(self, branch: str) -> bool:
        """Whether `branch` is a legal git branch name.

        Defers to `git check-ref-format --branch`, the authoritative validator,
        so names git would reject (spaces, `:`, `~`, a trailing `.`, a leading
        `-`, etc.) are caught before they reach `git worktree add -b`, which
        would otherwise fail with an opaque error deep inside async environment
        setup rather than at the point the name was chosen.
        """
        if not branch:
            return False
        try:
            self._run_git(["check-ref-format", "--branch", branch])
            return True
        except GitRepoError:
            return False

    def get_current_commit_hash(self) -> str:
        return self._run_git(["rev-parse", "HEAD"]).strip()

    def get_current_git_branch(self, is_detached_head_ok: bool = True) -> str:
        """Get the current git branch name for a repository."""
        args = ["rev-parse", "--abbrev-ref", "HEAD"]
        try:
            branch = self._run_git(args).strip()
        except GitRepoError as e:
            if e.branch_name == "" or e.branch_name is None:
                raise
            branch = e.branch_name
        if branch == "HEAD" and (not is_detached_head_ok):
            message = "in a detached HEAD state, which is not allowed in this context"
            raise GitRepoError(message=message, operation="git " + " ".join(args), repo_url=self.get_repo_url())
        return branch

    @log_runtime_decorator("get_all_branches")
    def get_all_branches(self) -> list[str]:
        # Enumerate real local branches (refs/heads/) in alphabetical order.
        # We use `for-each-ref` (plumbing) rather than `git branch` (porcelain)
        # because, in a detached-HEAD state, `git branch` prepends a placeholder
        # line like "(HEAD detached at <ref>)" that is not a branch. That
        # placeholder would otherwise surface in the source-branch picker and, if
        # selected, be passed to `git worktree add` as a ref git rejects.
        all_branches_result = self._run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
        all_branches = [b.strip() for b in all_branches_result.strip().split("\n") if b.strip()]

        if not all_branches:
            # fallback to current branch if no branches found
            current = self.get_current_git_branch()
            return [current] if current and current != "HEAD" else []

        return all_branches

    def get_remote_branches(self) -> list[str]:
        """Get a list of remote-tracking branches, excluding HEAD pointer entries."""
        output = self._run_git(["branch", "-r", "--format=%(refname:short)"])
        remote_branches: list[str] = []
        for line in output.splitlines():
            branch = line.strip()
            if not branch:
                continue
            # Skip HEAD pointer entries like "origin/HEAD -> origin/main" or "origin/HEAD".
            if branch.endswith("/HEAD") or "HEAD ->" in line:
                continue
            remote_branches.append(branch)
        return remote_branches


class LocalReadOnlyGitRepo(_ReadOnlyGitRepoSharedMethods):
    repo_path: Path
    concurrency_group: ConcurrencyGroup
    log_command: bool = True

    def get_repo_path(self) -> Path:
        """Get the path to the git repository."""
        return self.repo_path

    def get_repo_url(self) -> AnyUrl:
        return AnyUrl(f"file://{self.repo_path}")

    def has_any_commits(self) -> bool:
        """Check if repository has any commits. Returns False if not initialized or no commits exist."""
        if not (self.repo_path / ".git").exists():
            return False
        try:
            self.get_current_commit_hash()
            return True
        except GitRepoError:
            return False

    def _run_git(self, args: list[str]) -> str:
        """Run a git command in the specified repository."""
        try:
            cmd_to_run = ["git"] + args
            _, result_stdout, _ = run_git_command_local(
                self.concurrency_group,
                cmd_to_run,
                self.repo_path,
                is_retry_safe=False,
                log_command=self.log_command,
            )
            return result_stdout
        except FileNotFoundError as e:
            raise GitRepoNotFoundError(self.repo_path) from e
        except (GitCommandFailure, ProcessError) as e:
            if not self.repo_path.exists():
                raise GitRepoNotFoundError(self.repo_path) from e
            branch_name = None
            message = "Git command failed"
            try:
                cmd_to_run = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
                _, result_stdout, _ = run_git_command_local(
                    self.concurrency_group,
                    cmd_to_run,
                    self.repo_path,
                    is_retry_safe=False,
                    log_command=self.log_command,
                )
                branch_name = result_stdout.strip()
            except Exception as e2:
                if isinstance(e2, FileNotFoundError):
                    raise GitRepoNotFoundError(self.repo_path) from e2
                if isinstance(e2, ProcessSetupError) and not self.repo_path.exists():
                    raise GitRepoNotFoundError(self.repo_path) from e
                if isinstance(e2, ProcessError) and "unknown revision or path not in the working tree" in e.stderr:
                    message += " (repository appears to be empty, no commits yet)"
                else:
                    message += f" (failed to get current branch name for error reporting: {e})"
            raise GitRepoError(
                message=message,
                operation=" ".join(args),
                branch_name=branch_name,
                repo_url=self.get_repo_url(),
                exit_code=getattr(e, "returncode", -1),
                stderr=e.stderr,
            ) from e


class _WritableGitRepoSharedMethods(_GitRepoSharedMethods, WritableGitRepo, ABC):
    pass


class LocalWritableGitRepo(LocalReadOnlyGitRepo, _WritableGitRepoSharedMethods):
    @classmethod
    def from_new_repository(
        cls,
        repo_path: Path,
        concurrency_group: ConcurrencyGroup,
        user_email: str | None = None,
        user_name: str | None = None,
    ) -> "LocalWritableGitRepo":
        """Factory method that creates a NEW git repository and returns a LocalWritableGitRepo wrapper for it.

        This method runs `git init` to create a fresh repository at the specified path.
        For wrapping an EXISTING repository, use the regular constructor: LocalWritableGitRepo(repo_path, concurrency_group)

        Args:
            repo_path: Path where the new repository will be initialized (directory must exist but should not contain a .git folder)
            concurrency_group: ConcurrencyGroup to use for running git commands
            user_email: Optional email to configure for the repository. If not provided, uses global git config.
            user_name: Optional name to configure for the repository. If not provided, uses global git config.

        Returns:
            LocalWritableGitRepo: A wrapper for the newly created repository

        Raises:
            GitRepoError: If the directory doesn't exist, already contains a git repository, or initialization fails
        """
        if (repo_path / ".git").exists():
            raise GitRepoError(
                message=f"Directory is already a git repository: {repo_path}",
                operation="init",
                repo_url=AnyUrl(f"file://{repo_path}"),
                exit_code=None,
                stderr="",
            )

        if not repo_path.exists():
            raise GitRepoError(
                message=f"Directory does not exist: {repo_path}",
                operation="init",
                repo_url=None,
                exit_code=None,
                stderr="",
            )

        try:
            _result = concurrency_group.run_process_to_completion(
                command=["git", "init"], cwd=repo_path, is_checked_after=True
            )
            logger.debug("Initialized git repository at: {}", repo_path)
        except ProcessError as e:
            raise GitRepoError(
                message="Failed to initialize git repository",
                operation="init",
                repo_url=AnyUrl(f"file://{repo_path}"),
                exit_code=e.returncode,
                stderr=e.stderr,
            ) from e

        # Only configure user.email and user.name if explicitly provided
        if user_email is not None and user_name is not None:
            try:
                concurrency_group.run_process_to_completion(
                    command=["git", "config", "user.email", user_email], cwd=repo_path, is_checked_after=True
                )
                concurrency_group.run_process_to_completion(
                    command=["git", "config", "user.name", user_name], cwd=repo_path, is_checked_after=True
                )
                # Log without the values — git identity is personal data and
                # the log file is bundled into bug-report diagnostics uploads.
                logger.debug("Configured git user.email and user.name for {}", repo_path)
            except ProcessError as e:
                raise GitRepoError(
                    message="Failed to configure git user",
                    operation="config",
                    repo_url=AnyUrl(f"file://{repo_path}"),
                    exit_code=e.returncode,
                    stderr=e.stderr,
                ) from e

        return cls(repo_path=repo_path, concurrency_group=concurrency_group)

    def stage_all_files(self) -> None:
        """Stage all files (git add -A)."""
        self._run_git(["add", "-A"])
        logger.debug("Staged all files in repository")

    def create_commit(self, message: str, allow_empty: bool = False) -> str:
        """Create a commit. Returns the commit hash."""
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")

        self._run_git(args)
        commit_hash = self.get_current_commit_hash()
        logger.debug("Created commit: {} ({})", message, commit_hash)
        return commit_hash


class DefaultGitRepoService(GitRepoService):
    """Default implementation of GitRepoService using direct git commands in an Environment."""

    @contextmanager
    def open_local_user_git_repo_for_read(
        self, project: Project, log_command: bool = True
    ) -> Generator[LocalReadOnlyGitRepo, None, None]:
        repo_path = project.get_local_user_path()
        yield LocalReadOnlyGitRepo(
            repo_path=repo_path, concurrency_group=self.concurrency_group, log_command=log_command
        )
