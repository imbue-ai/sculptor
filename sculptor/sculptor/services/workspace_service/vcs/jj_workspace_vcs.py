"""Version control for jj workspaces: jj-only checkouts (`.jj` and no `.git`) of a colocated repository.

Reads that only look at recorded history pass `IGNORE_WORKING_COPY`, so they
add no operation. Reads that must see the agent's edits snapshot once, read the
working-copy commit id, and pin every follow-up read to that commit. A
snapshotting read in a stale workspace raises `JjWorkingCopyStaleError`, unless
the interface gives the method a failure value of its own.
"""

import base64
import json
import shutil
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Any
from typing import assert_never

from loguru import logger

from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.interfaces.environments.errors import EnvironmentNotFoundError
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.vcs.checkout_paths import validate_checkout_relative_path
from sculptor.services.workspace_service.vcs.data_types import AgentVcsEnvironment
from sculptor.services.workspace_service.vcs.data_types import BranchDeletionPolicy
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import CommitFileChange
from sculptor.services.workspace_service.vcs.data_types import FileAtRefResult
from sculptor.services.workspace_service.vcs.data_types import GitOperationResult
from sculptor.services.workspace_service.vcs.data_types import PullRequestRefs
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.data_types import RefNameValidation
from sculptor.services.workspace_service.vcs.data_types import RevisionDiff
from sculptor.services.workspace_service.vcs.errors import CheckoutFilesUnavailableError
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_log_parsing import CommitFileStatus
from sculptor.services.workspace_service.vcs.git_repo_queries import does_ref_exist
from sculptor.services.workspace_service.vcs.git_repo_queries import is_well_formed_branch_name
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_data_types import JjHeadIdentity
from sculptor.services.workspace_service.vcs.jj_data_types import JjInitialBookmarkOutcome
from sculptor.services.workspace_service.vcs.jj_data_types import JjRevisionHistory
from sculptor.services.workspace_service.vcs.jj_data_types import JjRevisionRecord
from sculptor.services.workspace_service.vcs.jj_data_types import JjStackProjection
from sculptor.services.workspace_service.vcs.jj_data_types import JjStackRevision
from sculptor.services.workspace_service.vcs.jj_repo_queries import add_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import does_bookmark_exist
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_bookmarks
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_bookmarks
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_tracked_bookmark_names
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_workspaces
from sculptor.services.workspace_service.vcs.jj_repo_queries import read_remotes
from sculptor.services.workspace_service.vcs.jj_repo_queries import read_workspace_config_path
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_commit_id
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_trunk_symbol
from sculptor.services.workspace_service.vcs.jj_repo_queries import select_target_candidates
from sculptor.services.workspace_service.vcs.jj_repo_queries import set_workspace_config
from sculptor.services.workspace_service.vcs.jj_repo_queries import snapshot_working_copy
from sculptor.services.workspace_service.vcs.jj_revsets import JjRevset
from sculptor.services.workspace_service.vcs.jj_revsets import bookmark_name_of_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import is_full_commit_id
from sculptor.services.workspace_service.vcs.jj_revsets import local_bookmark_revset
from sculptor.services.workspace_service.vcs.jj_revsets import revset_for_base
from sculptor.services.workspace_service.vcs.jj_revsets import root_file_fileset
from sculptor.services.workspace_service.vcs.jj_revsets import working_copy_revset
from sculptor.services.workspace_service.vcs.jj_stack_projection import project_jj_stack
from sculptor.services.workspace_service.vcs.repo_urls import extract_remote_hostname
from sculptor.services.workspace_service.vcs.repo_urls import is_github_remote_url
from sculptor.services.workspace_service.vcs.repo_urls import parse_remote_owner_and_name
from sculptor.utils.build import get_jj_bin_dir

# `|| true` keeps a missing or unreachable origin from blocking workspace startup.
DEFAULT_JJ_WORKSPACE_SETUP_COMMAND = "jj git fetch --remote origin 2>/dev/null || true"

# Returns the user's configured limit, in MiB, on the size of a new file jj snapshots.
SnapshotSizeLimitReader = Callable[[], int]

_SNAPSHOT_MAX_NEW_FILE_SIZE_KEY = "snapshot.max-new-file-size"
_BYTES_PER_MEBIBYTE = 1024 * 1024
_STORE_LINK = Path(".jj") / "repo"
_WORKING_COPY = JjRevset("@")
# Far more revisions than any workspace's stack holds; it bounds a target that shares no history with the stack.
_MAX_STACK_REVISIONS = 500
_MAX_HISTORY_REVISIONS = 500
_FINGERPRINT_TIMEOUT_SECONDS = 5.0
_REFUSED_SNAPSHOT_ERROR_PREFIX = "jj did not snapshot this file: "
_ORIGIN_REMOTE = "origin"
_GH_REPO = "GH_REPO"
_GIT_CEILING_DIRECTORIES = "GIT_CEILING_DIRECTORIES"
_JJ_EDITOR = "JJ_EDITOR"
_EDITOR_THAT_FAILS = "false"
# The seam's file changes have no copy status, so a copy counts as an added file.
_FILE_STATUS_BY_JJ_STATUS: Mapping[str, CommitFileStatus] = {
    "modified": "M",
    "added": "A",
    "removed": "D",
    "renamed": "R",
    "copied": "A",
}
# Each template prints one JSON value per line: `json()` escapes every field, so a
# description or path containing a newline or tab cannot break the parse.
_FILE_PATH_TEMPLATE = 'json(path) ++ "\\n"'
_WORKING_COPY_TEMPLATE = (
    '"[" ++ json(commit_id) ++ "," ++ json(change_id) ++ "," ++ json(change_id.shortest().prefix())'
    + ' ++ "," ++ json(description.first_line()) ++ "," ++ json(empty) ++ "," ++ json(conflict)'
    + ' ++ "," ++ json(divergent) ++ "]\\n"'
)
_STACK_REVISION_TEMPLATE = (
    '"[" ++ json(self) ++ ",[" ++ local_bookmarks.filter(|b| !b.conflict()).map(|b| json(b.name())).join(",")'
    + ' ++ "]]\\n"'
)
_REVISION_RECORD_TEMPLATE = (
    '"[" ++ json(self)'
    + ' ++ ",[" ++ local_bookmarks.map(|b| json(b.name())).join(",") ++ "]"'
    + ' ++ ",[" ++ self.diff().files().map(|f| "[" ++ json(f.path()) ++ "," ++ json(f.status())'
    + ' ++ "," ++ json(f.source().path()) ++ "]").join(",") ++ "]"'
    + ' ++ ",[" ++ self.diff().stat().files().map(|f| "[" ++ json(f.path()) ++ "," ++ json(f.lines_added())'
    + ' ++ "," ++ json(f.lines_removed()) ++ "]").join(",") ++ "]"'
    + ' ++ "," ++ json(empty) ++ "," ++ json(conflict) ++ "," ++ json(divergent)'
    + ' ++ "," ++ json(change_id.shortest().prefix()) ++ "]\\n"'
)


class JjWorkspaceVcs(WorkspaceVcs):
    """Version control for workspaces that are jj workspaces of the user's colocated repository.

    The jj workspace is named by the checkout name. git runs only in the user's
    colocated repository, never in the jj workspace.
    """

    def __init__(self, jj: JjCli, git: GitCli, read_snapshot_max_new_file_size_mib: SnapshotSizeLimitReader) -> None:
        self._jj = jj
        self._git = git
        self._read_snapshot_max_new_file_size_mib = read_snapshot_max_new_file_size_mib

    def create_checkout(self, spec: CheckoutSpec) -> CheckoutLocation:
        """`jj workspace add` from `spec.base_ref`, then the workspace's own config.

        A jj workspace starts without a bookmark, so `spec.new_ref_name` is not
        created here. A workspace of the same name left behind by a lost
        environment is forgotten first.
        """
        if spec.base_ref is None:
            raise InvalidCheckoutSpecError("base_ref is required for a jj workspace")
        base_revset = revset_for_base(spec.base_ref)
        self._forget_lost_workspace(spec.repo_path, spec.checkout_name)
        spec.checkout_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(
            "Creating jj workspace {} at {} from {} (user repo: {})",
            spec.checkout_name,
            spec.checkout_path,
            spec.base_ref,
            spec.repo_path,
        )
        add_workspace(
            self._jj, spec.repo_path, name=spec.checkout_name, base_revset=base_revset, destination=spec.checkout_path
        )
        self._apply_workspace_config(spec.checkout_path)
        return CheckoutLocation(
            repo_path=spec.repo_path, checkout_path=spec.checkout_path, checkout_name=spec.checkout_name
        )

    def _forget_lost_workspace(self, repo_path: Path, name: str) -> None:
        if all(entry.name != name for entry in list_workspaces(self._jj, repo_path)):
            return
        logger.warning("Forgetting jj workspace {}, left behind by a lost environment, to re-create it", name)
        forget_workspace(self._jj, repo_path, name)

    def _apply_workspace_config(self, checkout_path: Path) -> None:
        max_new_file_size_bytes = self._read_snapshot_max_new_file_size_mib() * _BYTES_PER_MEBIBYTE
        set_workspace_config(self._jj, checkout_path, _SNAPSHOT_MAX_NEW_FILE_SIZE_KEY, str(max_new_file_size_bytes))

    def verify_checkout(self, location: CheckoutLocation) -> None:
        """Check the workspace still links to its repository's store, then re-apply its config."""
        if not (location.checkout_path / _STORE_LINK).is_file():
            raise EnvironmentNotFoundError(f"jj workspace {location.checkout_path} has no {_STORE_LINK}")
        self._apply_workspace_config(location.checkout_path)

    def remove_checkout(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        created_ref_name: str | None,
        deletion_policy: BranchDeletionPolicy,
    ) -> None:
        """Forget the jj workspace, apply `deletion_policy` to its own bookmarks, and delete its jj config.

        The workspace's own bookmarks are those on its stack, plus
        `created_ref_name` while it is an ancestor of the working copy, so a
        bookmark merged into the target still counts. The target's own name and
        any bookmark on another workspace's stack are never touched. Bookmarks
        are forgotten, never deleted, so no later push deletes a remote branch;
        the workspace's commits stay visible. Works when the checkout directory
        is already gone, though its jj config then stays behind.
        """
        config_path = self._read_workspace_config_path(location.checkout_path)
        try:
            bookmarks_to_forget = self._resolve_bookmarks_to_forget(
                location, target_ref, created_ref_name, deletion_policy
            )
        except VcsCommandError as e:
            logger.info("Cannot resolve the bookmarks of jj workspace {}; keeping them: {}", location.checkout_name, e)
            bookmarks_to_forget = []
        logger.debug(
            "Forgetting jj workspace {} and bookmarks {} (policy {}, user repo: {})",
            location.checkout_name,
            bookmarks_to_forget,
            deletion_policy,
            location.repo_path,
        )
        try:
            forget_workspace(self._jj, location.repo_path, location.checkout_name)
            forget_bookmarks(self._jj, location.repo_path, bookmarks_to_forget)
        except VcsCommandError as e:
            logger.info("Failed to forget jj workspace {}: {}", location.checkout_name, e)
        if config_path is not None:
            self._delete_workspace_config_directory(config_path.parent)

    def _read_workspace_config_path(self, checkout_path: Path) -> Path | None:
        try:
            return read_workspace_config_path(self._jj, checkout_path)
        except VcsCommandError as e:
            logger.debug("Cannot find the jj config of {}: {}", checkout_path, e)
            return None

    def _delete_workspace_config_directory(self, config_directory: Path) -> None:
        try:
            shutil.rmtree(config_directory)
        except OSError as e:
            logger.info("Failed to delete jj workspace config {}: {}", config_directory, e)

    def _resolve_bookmarks_to_forget(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        created_ref_name: str | None,
        deletion_policy: BranchDeletionPolicy,
    ) -> list[str]:
        match deletion_policy:
            case "never":
                return []
            case "always":
                return sorted(self._find_own_bookmarks(location, target_ref, created_ref_name))
            case "delete_if_safe":
                own_bookmarks = self._find_own_bookmarks(location, target_ref, created_ref_name)
                return self._filter_safe_to_forget(location.repo_path, own_bookmarks, target_ref)
            case _ as unreachable:
                assert_never(unreachable)

    def _find_own_bookmarks(
        self, location: CheckoutLocation, target_ref: str | None, created_ref_name: str | None
    ) -> set[str]:
        """The workspace's own bookmarks; empty when the repository no longer has the workspace."""
        repo_path = location.repo_path
        working_copy_commit_id = resolve_commit_id(self._jj, repo_path, working_copy_revset(location.checkout_name))
        if working_copy_commit_id is None:
            logger.debug("jj workspace {} has no working copy; keeping its bookmarks", location.checkout_name)
            return set()
        target_commit_id = self._resolve_target_commit_id(repo_path, target_ref)
        own_bookmarks = self._read_bookmark_names(
            repo_path, _stack_revset(JjRevset(working_copy_commit_id), target_commit_id)
        )
        if created_ref_name is not None and created_ref_name in self._read_bookmark_names(
            repo_path, JjRevset(f"{local_bookmark_revset(created_ref_name)} & ::{working_copy_commit_id}")
        ):
            own_bookmarks.add(created_ref_name)
        own_bookmarks.discard(bookmark_name_of_symbol(target_ref))
        own_bookmarks -= self._read_bookmarks_on_other_stacks(repo_path, location.checkout_name, target_commit_id)
        return own_bookmarks

    def _read_bookmark_names(self, repo_dir: Path, revset: JjRevset) -> set[str]:
        """The unconflicted local bookmarks on `revset`."""
        return {
            bookmark for revision in self._read_stack_revisions(repo_dir, revset) for bookmark in revision.bookmarks
        }

    def _read_bookmarks_on_other_stacks(
        self, repo_path: Path, workspace_name: str, target_commit_id: str | None
    ) -> set[str]:
        """The bookmarks on the stack of any other workspace, including the user's own checkout."""
        other_working_copies = [
            f"present({working_copy_revset(entry.name)})"
            for entry in list_workspaces(self._jj, repo_path)
            if entry.name != workspace_name
        ]
        if not other_working_copies:
            return set()
        return self._read_bookmark_names(
            repo_path, _stack_revset(JjRevset(" | ".join(other_working_copies)), target_commit_id)
        )

    def _filter_safe_to_forget(
        self, repo_path: Path, bookmark_names: AbstractSet[str], target_ref: str | None
    ) -> list[str]:
        """The bookmarks that are merged into the target, or that track a remote bookmark on the same commit."""
        if not bookmark_names:
            return []
        target_commit_id = self._resolve_target_commit_id(repo_path, target_ref)
        bookmarks = list_bookmarks(self._jj, repo_path)
        local_commit_id_by_name = {
            bookmark.name: bookmark.commit_id for bookmark in bookmarks if bookmark.remote is None
        }
        fully_pushed = {
            bookmark.name
            for bookmark in bookmarks
            if bookmark.remote is not None
            and bookmark.is_tracked
            and bookmark.commit_id is not None
            and bookmark.commit_id == local_commit_id_by_name.get(bookmark.name)
        }
        if target_commit_id is None:
            merged: set[str] = set()
        else:
            named_bookmarks = " | ".join(local_bookmark_revset(name) for name in sorted(bookmark_names))
            merged = self._read_bookmark_names(repo_path, JjRevset(f"::{target_commit_id} & ({named_bookmarks})"))
        safe = sorted(name for name in bookmark_names if name in fully_pushed or name in merged)
        unsafe = sorted(set(bookmark_names) - set(safe))
        if unsafe:
            logger.info("Keeping bookmarks {}: neither merged into the target nor fully pushed", unsafe)
        return safe

    def resolve_default_target(self, repo_path: Path) -> str | None:
        """The remote bookmark on `trunk()`, such as `main@origin`; without one, the local `main` or `master`."""
        try:
            return resolve_trunk_symbol(self._jj, repo_path)
        except VcsCommandError as e:
            logger.debug("Cannot resolve a default target in {}: {}", repo_path, e)
            return None

    def list_target_candidates(self, repo_path: Path) -> list[str]:
        """Every local and remote bookmark that points at one commit, as a jj symbol such as `main@origin`."""
        return select_target_candidates(list_bookmarks(self._jj, repo_path))

    def validate_new_ref_name(self, repo_path: Path, ref_name: str) -> RefNameValidation:
        """A bookmark name must be a valid git branch name without `@`, and unused locally, on every remote and in git.

        git's own branches are checked too because jj imports a branch made in
        the colocated checkout only when a jj command next runs there.
        """
        if not ref_name or "@" in ref_name or not is_well_formed_branch_name(self._git, repo_path, ref_name):
            return RefNameValidation(ref_name=ref_name, status=RefNameStatus.MALFORMED)
        if does_bookmark_exist(self._jj, repo_path, ref_name) or does_ref_exist(
            self._git, repo_path, f"refs/heads/{ref_name}"
        ):
            return RefNameValidation(ref_name=ref_name, status=RefNameStatus.ALREADY_EXISTS)
        return RefNameValidation(ref_name=ref_name, status=RefNameStatus.AVAILABLE)

    def resolve_base_commit_id(self, repo_path: Path, base_ref: str) -> str | None:
        """The commit a bookmark symbol or full commit id names; None for anything else."""
        try:
            return resolve_commit_id(self._jj, repo_path, revset_for_base(base_ref))
        except InvalidRevisionError:
            return None
        except VcsCommandError as e:
            logger.debug("Cannot resolve {} in {}: {}", base_ref, repo_path, e)
            return None

    def default_setup_command(self) -> str:
        return DEFAULT_JJ_WORKSPACE_SETUP_COMMAND

    def read_identity(
        self, location: CheckoutLocation, target_ref: str | None, requested_ref_name: str | None
    ) -> JjHeadIdentity:
        """The working copy as last snapshotted, and the bookmarks on the workspace's stack."""
        checkout = location.checkout_path
        result = self._jj.run(
            ["log", "--no-graph", "-r", _WORKING_COPY, "-T", _WORKING_COPY_TEMPLATE],
            checkout,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        )
        commit_id, change_id, change_id_prefix, description_first_line, is_empty, has_conflict, is_divergent = (
            json.loads(result.stdout)
        )
        projection = self._project_stack(checkout, commit_id, target_ref, requested_ref_name)
        return JjHeadIdentity(
            working_copy_change_id=change_id,
            working_copy_change_id_prefix=change_id_prefix,
            description_first_line=description_first_line,
            is_working_copy_empty=is_empty,
            bookmarks=projection.bookmarks,
            primary_bookmark=projection.primary_bookmark,
            unbookmarked_revision_count=projection.unbookmarked_revision_count,
            has_conflict=has_conflict,
            is_divergent=is_divergent,
        )

    def get_pull_request_refs(
        self, location: CheckoutLocation, target_ref: str | None, requested_ref_name: str | None
    ) -> PullRequestRefs:
        """The stack's bookmarks, most likely PR head first, never the target's own name, with that name as the base.

        Raises `VcsCommandError` when jj cannot read the stack, so PR polling sees the failure.
        """
        checkout = location.checkout_path
        commit_id = self._read_working_copy_commit_id(checkout)
        projection = self._project_stack(checkout, commit_id, target_ref, requested_ref_name)
        return PullRequestRefs(
            head_ref_names=projection.pr_head_candidates, base_ref_name=bookmark_name_of_symbol(target_ref)
        )

    def create_initial_bookmark(
        self, location: CheckoutLocation, target_ref: str | None, requested_ref_name: str
    ) -> JjInitialBookmarkOutcome:
        """Create `requested_ref_name` on the stack's newest described revision, unless the stack has a bookmark already.

        Snapshots first, so the agent's last edits are in the bookmarked change.
        Leaves the stack alone while its work is undescribed, while two described
        revisions are both newest, and when the name is malformed or taken locally,
        on a remote or in git. Raises `JjWorkingCopyStaleError` when the
        workspace is stale.
        """
        checkout = location.checkout_path
        working_copy = snapshot_working_copy(self._jj, checkout)
        projection = self._project_stack(checkout, working_copy.commit_id, target_ref, requested_ref_name)
        if projection.bookmarks:
            return JjInitialBookmarkOutcome.STACK_HAS_A_BOOKMARK
        if len(projection.newest_described_commit_ids) != 1:
            return JjInitialBookmarkOutcome.NO_SINGLE_NEWEST_DESCRIBED_REVISION
        if self.validate_new_ref_name(location.repo_path, requested_ref_name).status is not RefNameStatus.AVAILABLE:
            return JjInitialBookmarkOutcome.NAME_UNAVAILABLE
        (newest_described_commit_id,) = projection.newest_described_commit_ids
        logger.debug("Creating bookmark {} on {} in {}", requested_ref_name, newest_described_commit_id, checkout)
        self._jj.run(
            ["bookmark", "create", requested_ref_name, "-r", newest_described_commit_id],
            checkout,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        )
        return JjInitialBookmarkOutcome.CREATED

    def _read_working_copy_commit_id(self, checkout: Path) -> str:
        """The working-copy commit as last snapshotted."""
        result = self._jj.run(
            ["log", "--no-graph", "-r", _WORKING_COPY, "-T", "commit_id"],
            checkout,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        )
        return result.stdout.strip()

    def _project_stack(
        self, repo_dir: Path, working_copy_commit_id: str, target_ref: str | None, requested_ref_name: str | None
    ) -> JjStackProjection:
        stack = _stack_revset(JjRevset(working_copy_commit_id), self._resolve_target_commit_id(repo_dir, target_ref))
        revisions = self._read_stack_revisions(repo_dir, stack)
        has_bookmarks = any(revision.bookmarks for revision in revisions)
        tracked_bookmark_names = list_tracked_bookmark_names(self._jj, repo_dir, stack) if has_bookmarks else set()
        return project_jj_stack(
            revisions,
            working_copy_commit_id,
            requested_ref_name,
            bookmark_name_of_symbol(target_ref),
            tracked_bookmark_names,
        )

    def _resolve_target_commit_id(self, repo_dir: Path, target_ref: str | None) -> str | None:
        """The one commit `target_ref` names; None when it is unset, malformed, absent or conflicted."""
        if target_ref is None:
            return None
        try:
            target_revset = revset_for_base(target_ref)
        except InvalidRevisionError:
            return None
        return resolve_commit_id(self._jj, repo_dir, target_revset)

    def _read_stack_revisions(self, repo_dir: Path, stack: JjRevset) -> list[JjStackRevision]:
        result = self._jj.run(
            ["log", "--no-graph", "--limit", str(_MAX_STACK_REVISIONS), "-r", stack, "-T", _STACK_REVISION_TEMPLATE],
            repo_dir,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        )
        revisions: list[JjStackRevision] = []
        for line in result.stdout.splitlines():
            commit, bookmarks = json.loads(line)
            revisions.append(
                JjStackRevision(
                    commit_id=commit["commit_id"],
                    parent_commit_ids=tuple(commit["parents"]),
                    bookmarks=tuple(bookmarks),
                    is_described=commit["description"] != "",
                )
            )
        return revisions

    def compute_diff_artifact(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        context_lines: int,
    ) -> DiffArtifact:
        """Snapshot once, then diff the working-copy commit `W` against its parents and, with a target, its fork point.

        jj tracks every file it snapshots, so new files appear in both diffs.
        Files jj refuses to snapshot, such as ones over the size limit, are
        reported in `file_errors`.
        """
        if not isinstance(context_lines, int) or context_lines < 0:
            raise ValueError(f"context_lines must be a non-negative integer, got {context_lines!r}")
        checkout = location.checkout_path
        working_copy = snapshot_working_copy(self._jj, checkout)
        diff_options = ["--git", "--context", str(context_lines)]
        uncommitted_diff = self._run_diff(checkout, ["-r", working_copy.commit_id, *diff_options])
        target_commit_id = self._resolve_target_commit_id(checkout, target_ref)
        fork_point = (
            None
            if target_commit_id is None
            else self._find_fork_point(checkout, target_commit_id, working_copy.commit_id)
        )
        if fork_point is None:
            target_branch_diff = ""
        else:
            target_branch_diff = self._run_diff(
                checkout, ["--from", fork_point, "--to", working_copy.commit_id, *diff_options]
            )
        return DiffArtifact(
            uncommitted_diff=uncommitted_diff.strip(),
            uncommitted_diff_base=working_copy.sole_parent_commit_id or "",
            target_branch_diff=target_branch_diff.strip(),
            target_branch_merge_base=fork_point or "",
            file_errors={
                path: f"{_REFUSED_SNAPSHOT_ERROR_PREFIX}{reason}"
                for path, reason in working_copy.refused_files.items()
            },
        )

    def _run_diff(self, checkout: Path, options: Sequence[str]) -> str:
        return self._jj.run(["diff", *options], checkout, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY).stdout

    def _find_fork_point(self, repo_dir: Path, other_commit_id: str, working_copy_commit_id: str) -> str | None:
        """The newest common ancestor of the working copy and `other_commit_id`."""
        fork_point_revset = JjRevset(f"latest(fork_point({other_commit_id} | {working_copy_commit_id}))")
        return resolve_commit_id(self._jj, repo_dir, fork_point_revset)

    def get_revision_history(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        base_commit_id: str | None,
    ) -> JjRevisionHistory:
        """The revisions after the fork point with the target, up to and including the working copy, newest first.

        `base_commit_id` stands in for a target that is unset or names no commit.
        The working copy is snapshotted first, so its record shows the agent's
        latest edits. Raises `JjWorkingCopyStaleError` when the workspace is stale.
        """
        working_copy = snapshot_working_copy(self._jj, location.checkout_path)
        return self._read_revision_history(location.checkout_path, target_ref, base_commit_id, working_copy.commit_id)

    def get_recorded_revision_history(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        base_commit_id: str | None,
    ) -> JjRevisionHistory:
        """The same revisions as `get_revision_history`, with the working copy as the repository last recorded it.

        Nothing is snapshotted, so this also reads a stale workspace, whose files
        jj will not snapshot until its working copy is updated.
        """
        checkout = location.checkout_path
        working_copy_commit_id = resolve_commit_id(self._jj, checkout, _WORKING_COPY)
        assert working_copy_commit_id is not None, "a jj workspace always has a working-copy commit"
        return self._read_revision_history(checkout, target_ref, base_commit_id, working_copy_commit_id)

    def _read_revision_history(
        self,
        checkout: Path,
        target_ref: str | None,
        base_commit_id: str | None,
        working_copy_commit_id: str,
    ) -> JjRevisionHistory:
        fork_from = self._resolve_target_commit_id(checkout, target_ref) or self._resolve_target_commit_id(
            checkout, base_commit_id
        )
        fork_point = None if fork_from is None else self._find_fork_point(checkout, fork_from, working_copy_commit_id)
        if fork_point is None:
            return JjRevisionHistory(revisions=(), fork_point=None)
        result = self._jj.run(
            [
                "log",
                "--no-graph",
                "--limit",
                str(_MAX_HISTORY_REVISIONS),
                "-r",
                f"{fork_point}..{working_copy_commit_id}",
                "-T",
                _REVISION_RECORD_TEMPLATE,
            ],
            checkout,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        )
        revisions = tuple(
            _parse_revision_record(json.loads(line), working_copy_commit_id) for line in result.stdout.splitlines()
        )
        return JjRevisionHistory(revisions=revisions, fork_point=fork_point)

    def get_revision_diff(self, location: CheckoutLocation, commit_id: str) -> RevisionDiff:
        """The diff `jj diff -r` shows for one revision: a merge is diffed against its merged parents."""
        checkout = location.checkout_path
        if not is_full_commit_id(commit_id):
            raise InvalidRevisionError(f"Not a full jj commit id: {commit_id!r}")
        result = self._jj.run(
            ["log", "--no-graph", "-r", f"present({commit_id})", "-T", "json(self)"],
            checkout,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        )
        if not result.stdout:
            raise InvalidRevisionError(f"Not a commit: {commit_id}")
        parent_commit_ids = json.loads(result.stdout)["parents"]
        try:
            diff = self._run_diff(checkout, ["-r", commit_id, "--git"])
        except VcsCommandError as e:
            logger.debug("Cannot diff revision {}: {}", commit_id, e)
            diff = ""
        return RevisionDiff(
            diff=diff,
            commit_id=commit_id,
            parent_commit_id=parent_commit_ids[0] if len(parent_commit_ids) == 1 else None,
        )

    def list_files(self, location: CheckoutLocation) -> list[str]:
        """Every file in the snapshotted working copy; files jj refuses to snapshot are not in it."""
        checkout = location.checkout_path
        try:
            working_copy = snapshot_working_copy(self._jj, checkout)
            result = self._jj.run(
                ["file", "list", "-r", working_copy.commit_id, "-T", _FILE_PATH_TEMPLATE],
                checkout,
                snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
            )
        except VcsCommandError as e:
            raise CheckoutFilesUnavailableError(checkout, str(e)) from e
        return sorted(json.loads(line) for line in result.stdout.splitlines())

    def read_file_at_revision(self, location: CheckoutLocation, file_path: str, revision: str) -> FileAtRefResult:
        """The file at `revision`, which must be a full commit id; base64-encoded when it contains a NUL byte.

        A revision is never evaluated as a revset, so anything else reads as a
        file not found there.
        """
        if not is_full_commit_id(revision):
            raise FileNotFoundAtRefError(file_path, revision, "not a full jj commit id")
        result = self._jj.run(
            ["file", "show", "-r", revision, root_file_fileset(file_path)],
            location.checkout_path,
            snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
            is_checked=False,
        )
        if result.returncode != 0:
            raise FileNotFoundAtRefError(file_path, revision, result.stderr)
        if "\0" in result.stdout:
            encoded = base64.b64encode(result.stdout.encode("utf-8", errors="surrogateescape")).decode("ascii")
            return FileAtRefResult(content=encoded, encoding="base64")
        return FileAtRefResult(content=result.stdout, encoding="utf-8")

    def discard_file_changes(self, location: CheckoutLocation, file_path: str) -> GitOperationResult:
        """`jj restore` the file from the working copy's parents, which deletes a file the working copy added."""
        checkout = location.checkout_path
        validation_error = validate_checkout_relative_path(file_path, checkout)
        if validation_error is not None:
            return GitOperationResult(success=False, stdout="", stderr="", error_message=validation_error)
        try:
            result = self._jj.run(
                ["restore", root_file_fileset(file_path)], checkout, snapshot=JjSnapshotPolicy.SNAPSHOT
            )
        except VcsCommandError as e:
            return GitOperationResult(success=False, stdout=e.stdout, stderr=e.stderr, error_message=str(e))
        return GitOperationResult(success=True, stdout=result.stdout, stderr=result.stderr)

    def agent_environment(self, location: CheckoutLocation) -> AgentVcsEnvironment:
        """jj-bin first on PATH, `GH_REPO` for a GitHub origin, a git ceiling above the checkout, and no editor.

        It touches no file and checks no readiness, so any caller may ask for it;
        jj-bin's link is kept where a process launches. gh finds no `.git` to read
        the repository from, so it needs `GH_REPO`. The ceiling makes a `git` run
        in the workspace fail instead of finding an enclosing repository.
        `JJ_EDITOR=false` makes a jj command that would open an editor fail at
        once instead of waiting on a terminal no one is at.
        """
        environment_variables = {_GIT_CEILING_DIRECTORIES: str(location.checkout_path.parent)}
        gh_repo = self._read_gh_repo(location.repo_path)
        if gh_repo is not None:
            environment_variables[_GH_REPO] = gh_repo
        return AgentVcsEnvironment(
            path_prefixes=(get_jj_bin_dir(),),
            environment_variables=environment_variables,
            chat_agent_environment_variables={_JJ_EDITOR: _EDITOR_THAT_FAILS},
        )

    def _read_gh_repo(self, repo_path: Path) -> str | None:
        """`HOST/OWNER/REPO` for a GitHub `origin`; None for any other origin or none."""
        try:
            origin_url = read_remotes(self._jj, repo_path).get(_ORIGIN_REMOTE)
        except VcsCommandError as e:
            logger.debug("Cannot read the remotes of {}: {}", repo_path, e)
            return None
        if origin_url is None or not is_github_remote_url(origin_url):
            return None
        owner_and_name = parse_remote_owner_and_name(origin_url)
        if owner_and_name is None:
            return None
        owner, name = owner_and_name
        return f"{extract_remote_hostname(origin_url)}/{owner}/{name}"

    def compute_change_fingerprint(self, location: CheckoutLocation) -> str | None:
        """The working-copy commit id after a snapshot, which changes with every edit and history change.

        None on failure, including in a stale workspace.
        """
        try:
            return snapshot_working_copy(
                self._jj, location.checkout_path, timeout=_FINGERPRINT_TIMEOUT_SECONDS
            ).commit_id
        except VcsCommandError as e:
            logger.debug("Change fingerprint failed in {}: {}", location.checkout_path, e)
            return None


def _stack_revset(working_copies: JjRevset, target_commit_id: str | None) -> JjRevset:
    """The working copies and their ancestors that are not the target's; without a target, their mutable ancestors."""
    if target_commit_id is None:
        return JjRevset(f"(::({working_copies}) & mutable()) | ({working_copies})")
    return JjRevset(f"(::({working_copies}) ~ ::{target_commit_id}) | ({working_copies})")


def _parse_revision_record(row: Sequence[Any], working_copy_commit_id: str) -> JjRevisionRecord:
    commit, bookmarks, changes, stats, is_empty, has_conflict, is_divergent, change_id_prefix = row
    lines_changed_by_path = {path: (added, removed) for path, added, removed in stats}
    files = tuple(
        CommitFileChange(
            path=path,
            status=_FILE_STATUS_BY_JJ_STATUS[status],
            old_path=source_path if status == "renamed" else None,
            additions=lines_changed_by_path.get(path, (0, 0))[0],
            deletions=lines_changed_by_path.get(path, (0, 0))[1],
        )
        for path, status, source_path in sorted(changes)
    )
    author = commit["author"]
    return JjRevisionRecord(
        change_id=commit["change_id"],
        change_id_prefix=change_id_prefix,
        commit_id=commit["commit_id"],
        description=commit["description"].removesuffix("\n"),
        author_name=author["name"],
        author_email=author["email"],
        timestamp=author["timestamp"],
        parent_commit_ids=tuple(commit["parents"]),
        bookmarks=tuple(bookmarks),
        files=files,
        is_empty=is_empty,
        has_conflict=has_conflict,
        is_divergent=is_divergent,
        is_working_copy=commit["commit_id"] == working_copy_commit_id,
    )
