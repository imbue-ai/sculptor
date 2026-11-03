"""`WorkspaceVcs` for git workspaces: in-place, clone and worktree."""

import base64
import hashlib
import re
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import assert_never

from loguru import logger

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.services.workspace_service.api import CommitFileChange
from sculptor.services.workspace_service.api import CommitRecord
from sculptor.services.workspace_service.api import FileAtRefResult
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.api import GitOperationResult
from sculptor.services.workspace_service.environment_manager.environments.clone_strategy import clone_repository
from sculptor.services.workspace_service.vcs.data_types import AgentVcsEnvironment
from sculptor.services.workspace_service.vcs.data_types import BranchDeletionPolicy
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import GitCommitHistory
from sculptor.services.workspace_service.vcs.data_types import GitHeadIdentity
from sculptor.services.workspace_service.vcs.data_types import PullRequestRefs
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.data_types import RefNameValidation
from sculptor.services.workspace_service.vcs.data_types import RevisionDiff
from sculptor.services.workspace_service.vcs.errors import CheckoutFilesUnavailableError
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_log_parsing import COMMIT_SEPARATOR_PREFIX
from sculptor.services.workspace_service.vcs.git_log_parsing import CommitFileStatus
from sculptor.services.workspace_service.vcs.git_log_parsing import parse_file_data_by_commit
from sculptor.services.workspace_service.vcs.git_log_parsing import parse_name_status_lines
from sculptor.services.workspace_service.vcs.git_log_parsing import parse_numstat_lines
from sculptor.services.workspace_service.vcs.git_repo_queries import does_ref_exist
from sculptor.services.workspace_service.vcs.git_repo_queries import read_head_identity
from sculptor.services.workspace_service.vcs.git_repo_queries import read_origin_url
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs

# Fetches the origin remote if present, and succeeds silently when there is no
# origin, so workspace startup is never blocked on it.
DEFAULT_GIT_WORKSPACE_SETUP_COMMAND = "git fetch origin 2>/dev/null || true"

_MAX_HISTORY_COMMITS = 500
_FINGERPRINT_TIMEOUT_SECONDS = 5.0
_COMMIT_ID_PATTERN = re.compile(r"^[0-9a-f]{4,40}$")
# Unit separator: cannot appear in commit subjects or author names.
_LOG_FIELD_SEPARATOR = "\x1f"
# One placeholder per field `_build_commit_record` unpacks, in the same order.
_COMMIT_LOG_PLACEHOLDERS = ("%H", "%h", "%s", "%aN", "%aE", "%aI", "%P")
_DEFAULT_REMOTE = "origin"
_DEFAULT_BRANCH_NAMES = ("main", "master")


class GitWorkspaceVcs(WorkspaceVcs):
    """Version control for workspaces that work in, clone, or add a worktree to a git repository."""

    def __init__(self, initialization_strategy: WorkspaceInitializationStrategy, git: GitCli) -> None:
        self._initialization_strategy = initialization_strategy
        self._git = git

    def create_checkout(self, spec: CheckoutSpec) -> CheckoutLocation:
        match self._initialization_strategy:
            case WorkspaceInitializationStrategy.IN_PLACE:
                return CheckoutLocation(repo_path=spec.repo_path, checkout_path=spec.repo_path)
            case WorkspaceInitializationStrategy.CLONE:
                self._create_clone(spec)
            case WorkspaceInitializationStrategy.WORKTREE:
                self._create_worktree(spec)
            case _ as unreachable:
                assert_never(unreachable)
        return CheckoutLocation(repo_path=spec.repo_path, checkout_path=spec.checkout_path)

    def _create_clone(self, spec: CheckoutSpec) -> None:
        clone_repository(
            source_repo_path=spec.repo_path,
            destination=spec.checkout_path,
            concurrency_group=self._git.concurrency_group,
            target_branch=spec.base_ref,
        )
        if spec.new_ref_name is not None and spec.new_ref_name.strip():
            self._git.run_git(["checkout", "-b", spec.new_ref_name], spec.checkout_path, is_read_only=False)

    def _create_worktree(self, spec: CheckoutSpec) -> None:
        """`git worktree add`: the checkout shares the user's `.git`, so its branch appears in their repository."""
        if spec.new_ref_name is None:
            raise InvalidCheckoutSpecError("new_ref_name is required for a worktree checkout")
        if spec.base_ref is None:
            raise InvalidCheckoutSpecError("base_ref is required for a worktree checkout")
        logger.debug(
            "Creating worktree at {} on branch {} from base {} (user repo: {})",
            spec.checkout_path,
            spec.new_ref_name,
            spec.base_ref,
            spec.repo_path,
        )
        self._git.run_git(
            ["worktree", "add", "-b", spec.new_ref_name],
            spec.repo_path,
            is_read_only=False,
            operands=[str(spec.checkout_path), spec.base_ref],
            timeout=None,
        )

    def verify_checkout(self, location: CheckoutLocation) -> None:
        """Git checkouts need no repair on resume."""

    def remove_checkout(
        self,
        location: CheckoutLocation,
        created_ref_name: str | None,
        deletion_policy: BranchDeletionPolicy,
    ) -> None:
        """Remove a worktree and apply `deletion_policy` to its branch; other kinds leave the repository alone.

        `created_ref_name` is the branch the worktree was created on. When it no
        longer exists because it was renamed inside the worktree (the agent's
        auto-rename does this), the policy applies to the branch the worktree has
        checked out instead, but only if git records it as that rename. When
        `created_ref_name` still exists it is the one deleted, even if the worktree
        has since switched branches: the policy only touches the branch this
        workspace created.
        """
        match self._initialization_strategy:
            case WorkspaceInitializationStrategy.IN_PLACE | WorkspaceInitializationStrategy.CLONE:
                return
            case WorkspaceInitializationStrategy.WORKTREE:
                pass
            case _ as unreachable:
                assert_never(unreachable)
        if created_ref_name is None:
            logger.info("Skipping worktree removal for {}: no branch was recorded for it", location.checkout_path)
            return
        try:
            self._remove_worktree(location, created_ref_name, deletion_policy)
        except VcsCommandError as e:
            logger.info("Failed to remove worktree {}: {}", location.checkout_path, e)

    def _remove_worktree(
        self, location: CheckoutLocation, created_ref_name: str, deletion_policy: BranchDeletionPolicy
    ) -> None:
        # Resolved before `git worktree remove`, which discards the worktree's HEAD.
        branch_to_delete = (
            None if deletion_policy == "never" else self._resolve_branch_to_delete(location, created_ref_name)
        )
        logger.debug(
            "Removing worktree at {} (deleting branch {}, policy {}, user repo: {})",
            location.checkout_path,
            branch_to_delete,
            deletion_policy,
            location.repo_path,
        )
        try:
            self._git.run_git(
                ["worktree", "remove"], location.repo_path, is_read_only=False, operands=[str(location.checkout_path)]
            )
        except VcsCommandError as e:
            logger.debug("git worktree remove failed, continuing: {}", e)

        if branch_to_delete is None:
            return
        branch_flag = "-d" if deletion_policy == "delete_if_safe" else "-D"
        try:
            self._git.run_git(
                ["branch", branch_flag], location.repo_path, is_read_only=False, operands=[branch_to_delete]
            )
        except VcsCommandError as e:
            logger.debug("Branch deletion failed (policy {}), continuing: {}", deletion_policy, e)

    def _resolve_branch_to_delete(self, location: CheckoutLocation, created_ref_name: str) -> str | None:
        """The created branch, or its recorded rename; None when neither can be identified."""
        if does_ref_exist(self._git, location.repo_path, f"refs/heads/{created_ref_name}"):
            return created_ref_name
        checked_out = self._read_checked_out_branch(location.checkout_path)
        if checked_out is None:
            logger.debug(
                "Branch {} no longer exists and the worktree's branch is unknown; not deleting", created_ref_name
            )
            return None
        if not self._is_recorded_rename_of(location.repo_path, checked_out, created_ref_name):
            logger.debug(
                "Branch {} no longer exists and {} (checked out in the worktree) is not recorded as its rename; not deleting",
                created_ref_name,
                checked_out,
            )
            return None
        logger.debug("Branch {} was renamed to {}; deleting the rename instead", created_ref_name, checked_out)
        return checked_out

    def _read_checked_out_branch(self, checkout_path: Path) -> str | None:
        """The branch checked out at `checkout_path`, or None if the checkout is gone or detached."""
        try:
            return read_head_identity(self._git, checkout_path).branch_name
        except VcsCommandError as e:
            logger.debug("Cannot read the branch of {}: {}", checkout_path, e)
            return None

    def _is_recorded_rename_of(self, repo_path: Path, branch_name: str, original_branch: str) -> bool:
        """Whether git records `branch_name` as a rename of `original_branch`.

        `git branch -m` appends `Branch: renamed refs/heads/<old> to refs/heads/<new>`
        to the new branch's reflog, which is the only local evidence tying a renamed
        branch to the one the workspace created. Anything else (an unrelated branch
        checked out after the created one was deleted, a second rename, reflogs
        turned off) reads as not attributable, so the branch is left alone.
        """
        result = self._git.run_git(
            ["reflog", "show", "--format=%gs"], repo_path, is_read_only=True, operands=[branch_name], is_checked=False
        )
        if result.returncode != 0:
            return False
        rename_entry = f"Branch: renamed refs/heads/{original_branch} to refs/heads/{branch_name}"
        return any(line.strip() == rename_entry for line in result.stdout.splitlines())

    def resolve_default_target(self, repo_path: Path) -> str | None:
        """`origin`'s default branch; without one, the local `main` or `master`.

        Clone checkouts get a synthetic `origin` seeded with the source's local
        branches, so for them the fallback is spelled `origin/<branch>`. In-place
        and worktree checkouts share the user's `.git`, so the bare local branch
        resolves directly.
        """
        try:
            remote_default = self._detect_default_branch_for_remote(repo_path, _DEFAULT_REMOTE)
            if remote_default is not None:
                return remote_default
            local_default = self._detect_local_main_or_master(repo_path)
        except VcsCommandError as e:
            logger.debug("Cannot resolve a default target in {}: {}", repo_path, e)
            return None
        if local_default is None:
            return None
        match self._initialization_strategy:
            case WorkspaceInitializationStrategy.CLONE:
                return f"{_DEFAULT_REMOTE}/{local_default}"
            case WorkspaceInitializationStrategy.IN_PLACE | WorkspaceInitializationStrategy.WORKTREE:
                return local_default
            case _ as unreachable:
                assert_never(unreachable)

    def _detect_default_branch_for_remote(self, repo_path: Path, remote: str) -> str | None:
        """`<remote>/HEAD` as set by `git remote set-head`, else `<remote>/main`, else `<remote>/master`."""
        result = self._git.run_git(
            ["symbolic-ref"], repo_path, is_read_only=True, operands=[f"refs/remotes/{remote}/HEAD"], is_checked=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().removeprefix("refs/remotes/")
        for branch_name in _DEFAULT_BRANCH_NAMES:
            if does_ref_exist(self._git, repo_path, f"refs/remotes/{remote}/{branch_name}"):
                return f"{remote}/{branch_name}"
        return None

    def _detect_local_main_or_master(self, repo_path: Path) -> str | None:
        for branch_name in _DEFAULT_BRANCH_NAMES:
            if does_ref_exist(self._git, repo_path, f"refs/heads/{branch_name}"):
                return branch_name
        return None

    def list_target_candidates(self, repo_path: Path) -> list[str]:
        """Remote-tracking branches of every remote; local branches when there are none."""
        remote_output = self._git.run_git(
            ["branch", "-r", "--format=%(refname:short)"], repo_path, is_read_only=True
        ).stdout
        remote_branches = [
            line.strip()
            for line in remote_output.splitlines()
            if line.strip() and not line.strip().endswith("/HEAD") and "HEAD ->" not in line
        ]
        if remote_branches:
            return remote_branches
        local_output = self._git.run_git(
            ["for-each-ref", "--format=%(refname:short)"], repo_path, is_read_only=True, operands=["refs/heads/"]
        ).stdout
        local_branches = [line.strip() for line in local_output.splitlines() if line.strip()]
        if local_branches:
            return local_branches
        # A repository with no commits has no branch refs, but its HEAD still names a branch.
        current_branch = read_head_identity(self._git, repo_path).branch_name
        return [] if current_branch is None else [current_branch]

    def validate_new_ref_name(self, repo_path: Path, ref_name: str) -> RefNameValidation:
        if not ref_name or not self._is_well_formed_branch_name(repo_path, ref_name):
            return RefNameValidation(ref_name=ref_name, status=RefNameStatus.MALFORMED)
        if does_ref_exist(self._git, repo_path, f"refs/heads/{ref_name}"):
            return RefNameValidation(ref_name=ref_name, status=RefNameStatus.ALREADY_EXISTS)
        return RefNameValidation(ref_name=ref_name, status=RefNameStatus.AVAILABLE)

    def _is_well_formed_branch_name(self, repo_path: Path, ref_name: str) -> bool:
        # `check-ref-format` rejects `--end-of-options`; `--branch` consumes the next
        # argument as the name, so a name starting with `-` is still not an option.
        result = self._git.run_git(
            ["check-ref-format", "--branch", ref_name], repo_path, is_read_only=True, is_checked=False
        )
        return result.returncode == 0

    def resolve_base_commit_id(self, repo_path: Path, base_ref: str) -> str | None:
        return self._resolve_commit_id(repo_path, base_ref)

    def default_setup_command(self) -> str:
        return DEFAULT_GIT_WORKSPACE_SETUP_COMMAND

    def read_identity(self, location: CheckoutLocation) -> GitHeadIdentity:
        return read_head_identity(self._git, location.checkout_path)

    def compute_diff_artifact(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        context_lines: int,
    ) -> DiffArtifact:
        """Diffs that cover untracked files too, with `-M` so a rename is one entry rather than a delete and an add.

        The target diff runs from the merge base with `target_ref` to the working
        tree, so it includes uncommitted work. The merge base is exposed so the
        frontend can fetch old-side content at the exact commit the diff's
        old-side line numbers refer to.
        """
        if not isinstance(context_lines, int) or context_lines < 0:
            raise ValueError(f"context_lines must be a non-negative integer, got {context_lines!r}")
        checkout = location.checkout_path
        context_flag = f"-U{context_lines}"
        untracked_diff = self._diff_untracked_files(checkout)

        uncommitted_diff = self._run_diff(["--no-pager", "diff", "-M", context_flag], checkout, "HEAD", "uncommitted")
        target_branch_diff = ""
        target_branch_merge_base = ""
        if target_ref is not None:
            merge_base = self._get_merge_base(checkout, target_ref)
            if merge_base is not None:
                target_branch_merge_base = merge_base
                target_branch_diff = self._run_diff(
                    ["--no-pager", "diff", "-M", context_flag], checkout, merge_base, "target-branch"
                )

        return DiffArtifact(
            uncommitted_diff=(uncommitted_diff + untracked_diff).strip(),
            target_branch_diff=(target_branch_diff + untracked_diff).strip() if target_branch_merge_base else "",
            target_branch_merge_base=target_branch_merge_base,
            file_errors=self._detect_file_errors(checkout),
        )

    def _run_diff(self, options: Sequence[str], checkout: Path, base: str, diff_kind: str) -> str:
        """A diff's output, or "" when git cannot produce it."""
        try:
            result = self._git.run_git(options, checkout, is_read_only=True, operands=[base], is_checked=False)
        except VcsCommandError as e:
            logger.debug("Failed to generate {} diff: {}", diff_kind, e)
            return ""
        # Exit 1 means the diff is non-empty; anything above is a real failure.
        if result.returncode > 1:
            logger.debug(
                "Unexpected returncode for {} diff: returncode={}, stderr={}",
                diff_kind,
                result.returncode,
                result.stderr[:500],
            )
        return result.stdout

    def _diff_untracked_files(self, checkout: Path) -> str:
        """A creation diff for every untracked regular file; symlinks and nested repositories are skipped."""
        try:
            listing = self._git.run_git(
                ["ls-files", "--others", "--exclude-standard", "-z"], checkout, is_read_only=True, is_checked=False
            )
        except VcsCommandError as e:
            logger.debug("Failed to list untracked files: {}", e)
            return ""
        diffs: list[str] = []
        for file_path in listing.stdout.split("\0"):
            if not file_path:
                continue
            path = checkout / file_path
            if path.is_symlink() or not path.is_file():
                continue
            try:
                result = self._git.run_git(
                    ["--no-pager", "diff", "--no-index"],
                    checkout,
                    is_read_only=True,
                    paths=["/dev/null", file_path],
                    is_checked=False,
                )
            except VcsCommandError as e:
                logger.debug("Failed to diff untracked file {}: {}", file_path, e)
                continue
            diffs.append(result.stdout)
        return "".join(diffs)

    def _get_merge_base(self, checkout: Path, target_ref: str) -> str | None:
        """The merge base of HEAD and `target_ref`, or None when there is none."""
        try:
            result = self._git.run_git(
                ["merge-base"], checkout, is_read_only=True, operands=["HEAD", target_ref], is_checked=False
            )
        except VcsCommandError as e:
            logger.debug("Cannot compute the merge base with {}: {}", target_ref, e)
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip()

    def _detect_file_errors(self, checkout: Path) -> dict[str, str]:
        """Files that cannot be diffed, such as files inside a nested repository."""
        try:
            result = self._git.run_git(
                ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                checkout,
                is_read_only=True,
                is_checked=False,
            )
        except VcsCommandError as e:
            logger.debug("Cannot list files to detect diff errors: {}", e)
            return {}
        if result.returncode != 0:
            return {}
        return {
            file_path: "Could not generate diff: file is inside a nested git repository"
            for file_path in result.stdout.split("\0")
            if file_path.strip() and "/.git/" in f"/{file_path}/" and not file_path.startswith(".git/")
        }

    def get_revision_history(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        base_commit_id: str | None,
    ) -> GitCommitHistory:
        """Commits on HEAD since its merge base with `target_ref`.

        The merge base moves forward with merges and rebases, so commits already
        on the target are excluded. `base_commit_id` stands in when there is no
        target or no merge base.
        """
        checkout = location.checkout_path
        merge_base = None if target_ref is None else self._get_merge_base(checkout, target_ref)
        fork_point = merge_base or base_commit_id
        if fork_point is None:
            return GitCommitHistory(commits=[], fork_point=None)
        revision_range = f"{fork_point}..HEAD"

        format_string = _LOG_FIELD_SEPARATOR.join(_COMMIT_LOG_PLACEHOLDERS)
        try:
            result = self._git.run_git(
                ["log", f"-n{_MAX_HISTORY_COMMITS}", f"--format={format_string}"],
                checkout,
                is_read_only=True,
                operands=[revision_range],
                is_checked=False,
            )
        except VcsCommandError as e:
            logger.debug("Cannot read the commit history since {}: {}", fork_point, e)
            return GitCommitHistory(commits=[], fork_point=fork_point)
        if result.returncode != 0 or not result.stdout.strip():
            return GitCommitHistory(commits=[], fork_point=fork_point)

        metadata_rows = [
            fields
            for fields in (line.split(_LOG_FIELD_SEPARATOR) for line in result.stdout.strip().split("\n"))
            if len(fields) == len(_COMMIT_LOG_PLACEHOLDERS)
        ]
        if not metadata_rows:
            return GitCommitHistory(commits=[], fork_point=fork_point)

        numstat_by_hash = parse_file_data_by_commit(
            self._read_log_file_data(checkout, revision_range, "--numstat"), parse_numstat_lines
        )
        status_by_hash = parse_file_data_by_commit(
            self._read_log_file_data(checkout, revision_range, "--name-status"), parse_name_status_lines
        )
        commits = [
            _build_commit_record(fields, numstat_by_hash.get(fields[0], {}), status_by_hash.get(fields[0], {}))
            for fields in metadata_rows
        ]
        return GitCommitHistory(commits=commits, fork_point=fork_point)

    def _read_log_file_data(self, checkout: Path, revision_range: str, file_flag: str) -> str:
        """`git log` output with per-commit file data, each commit introduced by a separator line."""
        try:
            result = self._git.run_git(
                ["log", f"-n{_MAX_HISTORY_COMMITS}", f"--format={COMMIT_SEPARATOR_PREFIX}%H", file_flag, "-M"],
                checkout,
                is_read_only=True,
                operands=[revision_range],
                is_checked=False,
            )
        except VcsCommandError as e:
            logger.debug("Cannot read {} for {}: {}", file_flag, revision_range, e)
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout

    def get_revision_diff(self, location: CheckoutLocation, commit_id: str) -> RevisionDiff:
        checkout = location.checkout_path
        if not _COMMIT_ID_PATTERN.match(commit_id):
            raise InvalidRevisionError(f"Invalid commit hash: {commit_id}")
        try:
            object_type = self._git.run_git(
                ["cat-file", "-t"], checkout, is_read_only=True, operands=[commit_id], is_checked=False
            )
        except VcsCommandError as e:
            raise InvalidRevisionError(f"Not a valid commit: {commit_id}") from e
        if object_type.returncode != 0 or object_type.stdout.strip() != "commit":
            raise InvalidRevisionError(f"Not a valid commit: {commit_id}")

        full_commit_id = self._resolve_commit_id(checkout, commit_id) or commit_id
        parent_commit_id = self._resolve_commit_id(checkout, f"{full_commit_id}^")
        if parent_commit_id is not None:
            options = ["--no-pager", "diff", "-M"]
            operand = f"{parent_commit_id}..{full_commit_id}"
        else:
            options = ["--no-pager", "diff-tree", "-p", "--root", "-M"]
            operand = full_commit_id
        try:
            result = self._git.run_git(options, checkout, is_read_only=True, operands=[operand], is_checked=False)
        except VcsCommandError as e:
            logger.debug("Cannot diff commit {}: {}", full_commit_id, e)
            diff = ""
        else:
            diff = result.stdout if result.returncode <= 1 else ""
        return RevisionDiff(diff=diff, commit_id=full_commit_id, parent_commit_id=parent_commit_id)

    def _resolve_commit_id(self, directory: Path, revision: str) -> str | None:
        """The full commit id `revision` names, or None when it names none."""
        try:
            result = self._git.run_git(
                ["rev-parse", "--verify", "--quiet"],
                directory,
                is_read_only=True,
                operands=[revision],
                is_checked=False,
            )
        except VcsCommandError as e:
            logger.debug("Cannot resolve {}: {}", revision, e)
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip()

    def list_files(self, location: CheckoutLocation) -> list[str]:
        checkout = location.checkout_path
        try:
            result = self._git.run_git(
                ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                checkout,
                is_read_only=True,
                is_checked=False,
            )
        except VcsCommandError as e:
            raise CheckoutFilesUnavailableError(checkout, str(e)) from e
        if result.returncode != 0:
            # A non-zero exit (e.g. index lock contention) must not read as an empty checkout.
            raise CheckoutFilesUnavailableError(
                checkout, result.stderr.strip() or f"git ls-files exited {result.returncode}"
            )
        return sorted(
            file_path
            for file_path in result.stdout.split("\0")
            if file_path.strip() and not file_path.startswith(".git/")
        )

    def read_file_at_revision(self, location: CheckoutLocation, file_path: str, revision: str) -> FileAtRefResult:
        """The file's content, base64-encoded when it contains a NUL byte."""
        result = self._git.run_git(
            ["--no-pager", "show"],
            location.checkout_path,
            is_read_only=True,
            operands=[f"{revision}:{file_path}"],
            is_checked=False,
        )
        if result.returncode != 0:
            raise FileNotFoundAtRefError(file_path, revision, result.stderr)
        if "\0" in result.stdout:
            encoded = base64.b64encode(result.stdout.encode("utf-8", errors="surrogateescape")).decode("ascii")
            return FileAtRefResult(content=encoded, encoding="base64")
        return FileAtRefResult(content=result.stdout, encoding="utf-8")

    def discard_file_changes(self, location: CheckoutLocation, file_path: str) -> GitOperationResult:
        """Restore a tracked file from HEAD, or delete an untracked one."""
        checkout = location.checkout_path
        validation_error = _validate_checkout_relative_path(file_path, checkout)
        if validation_error is not None:
            return GitOperationResult(success=False, stdout="", stderr="", error_message=validation_error)

        if self._is_file_tracked(checkout, file_path):
            options, operands = ["checkout"], ["HEAD"]
        else:
            options, operands = ["clean", "-f"], []
        try:
            result = self._git.run_git(
                options, checkout, is_read_only=False, operands=operands, paths=[file_path], is_checked=False
            )
        except VcsCommandError as e:
            return GitOperationResult(success=False, stdout=e.stdout, stderr=e.stderr, error_message=str(e))
        is_success = result.returncode == 0
        return GitOperationResult(
            success=is_success,
            stdout=result.stdout,
            stderr=result.stderr,
            error_message=None if is_success else f"Git command failed with exit code {result.returncode}",
        )

    def _is_file_tracked(self, checkout: Path, file_path: str) -> bool:
        try:
            result = self._git.run_git(
                ["ls-files", "--error-unmatch"], checkout, is_read_only=True, paths=[file_path], is_checked=False
            )
        except VcsCommandError as e:
            logger.debug("Cannot tell whether {} is tracked: {}", file_path, e)
            return False
        return result.returncode == 0

    def get_pull_request_refs(self, location: CheckoutLocation) -> PullRequestRefs:
        """The checked-out branch as the only head candidate, plus the origin URL.

        A detached HEAD has no candidate. Failures read as "nothing to look up",
        so PR polling reports no pull request rather than erroring.
        """
        checkout = location.checkout_path
        branch_name = self._read_checked_out_branch(checkout)
        try:
            origin_url = read_origin_url(self._git, checkout)
        except VcsCommandError as e:
            logger.debug("Cannot read the origin of {}: {}", checkout, e)
            origin_url = None
        return PullRequestRefs(head_ref_names=() if branch_name is None else (branch_name,), origin_url=origin_url)

    def agent_environment(self, location: CheckoutLocation) -> AgentVcsEnvironment:
        return AgentVcsEnvironment()

    def compute_change_fingerprint(self, location: CheckoutLocation) -> str | None:
        """A hash of `git status --porcelain` and HEAD; None on failure, so a transient error just skips a poll."""
        checkout = location.checkout_path
        try:
            status = self._git.run_git(
                ["status", "--porcelain"],
                checkout,
                is_read_only=True,
                is_checked=False,
                timeout=_FINGERPRINT_TIMEOUT_SECONDS,
            )
            head = self._git.run_git(
                ["rev-parse", "--verify"],
                checkout,
                is_read_only=True,
                operands=["HEAD"],
                is_checked=False,
                timeout=_FINGERPRINT_TIMEOUT_SECONDS,
            )
        except VcsCommandError as e:
            logger.debug("Change fingerprint failed in {}: {}", checkout, e)
            return None
        if status.returncode != 0 or head.returncode != 0:
            logger.debug(
                "Change fingerprint git commands failed in {} (status rc={}, rev-parse rc={})",
                checkout,
                status.returncode,
                head.returncode,
            )
            return None
        return hashlib.sha256((status.stdout + "\x00" + head.stdout).encode()).hexdigest()


def _build_commit_record(
    fields: Sequence[str],
    numstat: Mapping[str, tuple[int, int]],
    statuses: Mapping[str, tuple[CommitFileStatus, str | None]],
) -> CommitRecord:
    commit_hash, short_hash, message, author_name, author_email, timestamp, parents = fields
    files: list[CommitFileChange] = []
    for path in sorted(numstat.keys() | statuses.keys()):
        status, old_path = statuses.get(path, ("M", None))
        additions, deletions = numstat.get(path, (0, 0))
        files.append(
            CommitFileChange(path=path, status=status, old_path=old_path, additions=additions, deletions=deletions)
        )
    return CommitRecord(
        hash=commit_hash,
        short_hash=short_hash,
        message=message,
        author_name=author_name,
        author_email=author_email,
        timestamp=timestamp,
        parent_hashes=parents.split() if parents else [],
        files=files,
    )


def _validate_checkout_relative_path(file_path: str, checkout: Path) -> str | None:
    """Why `file_path` may not be touched, or None when it stays inside `checkout`."""
    if file_path.startswith("/"):
        return "Absolute paths are not allowed"
    if not (checkout / file_path).resolve().is_relative_to(checkout.resolve()):
        return "Path traversal is not allowed"
    return None
