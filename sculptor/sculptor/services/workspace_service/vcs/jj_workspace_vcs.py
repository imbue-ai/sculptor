"""Version control for jj workspaces: jj-only checkouts (`.jj` and no `.git`) of a colocated repository.

Reads that only look at recorded history pass `IGNORE_WORKING_COPY`, so they
add no operation. Reads that must see the agent's edits snapshot once, read the
working-copy commit id, and pin every follow-up read to that commit. A
snapshotting read in a stale workspace raises `JjWorkingCopyStaleError`, unless
the interface gives the method a failure value of its own.
"""

import json
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from sculptor.interfaces.environments.errors import EnvironmentNotFoundError
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import PullRequestRefs
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.data_types import RefNameValidation
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_repo_queries import does_ref_exist
from sculptor.services.workspace_service.vcs.git_repo_queries import is_well_formed_branch_name
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmarkSymbol
from sculptor.services.workspace_service.vcs.jj_data_types import JjHeadIdentity
from sculptor.services.workspace_service.vcs.jj_data_types import JjStackProjection
from sculptor.services.workspace_service.vcs.jj_data_types import JjStackRevision
from sculptor.services.workspace_service.vcs.jj_repo_queries import add_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import does_bookmark_exist
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_bookmarks
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_tracked_bookmark_names
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_workspaces
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_commit_id
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_trunk_symbol
from sculptor.services.workspace_service.vcs.jj_repo_queries import set_workspace_config
from sculptor.services.workspace_service.vcs.jj_revsets import JjRevset
from sculptor.services.workspace_service.vcs.jj_revsets import format_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import parse_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import revset_for_base
from sculptor.services.workspace_service.vcs.jj_stack_projection import project_jj_stack

# Fetches the origin remote if present, and succeeds silently when there is no
# origin, so workspace startup is never blocked on it.
DEFAULT_JJ_WORKSPACE_SETUP_COMMAND = "jj git fetch --remote origin 2>/dev/null || true"

# Returns the user's configured limit, in MiB, on the size of a new file jj snapshots.
SnapshotSizeLimitReader = Callable[[], int]

_SNAPSHOT_MAX_NEW_FILE_SIZE_KEY = "snapshot.max-new-file-size"
_BYTES_PER_MEBIBYTE = 1024 * 1024
_STORE_LINK = Path(".jj") / "repo"
_WORKING_COPY = JjRevset("@")
# Far more revisions than any workspace's stack holds; it bounds a target that shares no history with the stack.
_MAX_STACK_REVISIONS = 500
# One JSON array per line: commit id, change id, shortest unique change id prefix,
# first line of the description, then the empty, conflict and divergent flags.
_WORKING_COPY_TEMPLATE = (
    '"[" ++ json(commit_id) ++ "," ++ json(change_id) ++ "," ++ json(change_id.shortest().prefix())'
    + ' ++ "," ++ json(description.first_line()) ++ "," ++ json(empty) ++ "," ++ json(conflict)'
    + ' ++ "," ++ json(divergent) ++ "]\\n"'
)
# One JSON array per line: the commit, then the names of its unconflicted local bookmarks.
_STACK_REVISION_TEMPLATE = (
    '"[" ++ json(self) ++ ",[" ++ local_bookmarks.filter(|b| !b.conflict()).map(|b| json(b.name())).join(",")'
    + ' ++ "]]\\n"'
)


class JjWorkspaceVcs:
    """Version control for workspaces that are jj workspaces of the user's colocated repository.

    The jj workspace is named by the checkout name. git is used only in the
    user's colocated repository, to check branch names as git does.
    """

    def __init__(self, jj: JjCli, git: GitCli, read_snapshot_max_new_file_size_mib: SnapshotSizeLimitReader) -> None:
        self._jj = jj
        self._git = git
        self._read_snapshot_max_new_file_size_mib = read_snapshot_max_new_file_size_mib

    def create_checkout(self, spec: CheckoutSpec) -> CheckoutLocation:
        """`jj workspace add` from `spec.base_ref`, then the workspace's own config.

        A jj workspace starts without a bookmark: Sculptor sets `spec.new_ref_name`
        later, once the agent has described a revision. A workspace of the same
        name left behind by a lost environment is forgotten first.
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

    def resolve_default_target(self, repo_path: Path) -> str | None:
        """The remote bookmark on `trunk()`, such as `main@origin`; without one, the local `main` or `master`."""
        try:
            return resolve_trunk_symbol(self._jj, repo_path)
        except VcsCommandError as e:
            logger.debug("Cannot resolve a default target in {}: {}", repo_path, e)
            return None

    def list_target_candidates(self, repo_path: Path) -> list[str]:
        """Every local and remote bookmark that points at one commit, as a jj symbol such as `main@origin`."""
        return [
            format_bookmark_symbol(JjBookmarkSymbol(name=bookmark.name, remote=bookmark.remote))
            for bookmark in list_bookmarks(self._jj, repo_path)
            if bookmark.commit_id is not None
        ]

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
        """The working copy as last snapshotted, and the bookmarks on the workspace's stack.

        The stack is the working copy's ancestors that are not the target's; with
        no resolvable target, its mutable ancestors.
        """
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
        """The stack's bookmarks, most likely PR head first, never the target's own name.

        Failures read as "nothing to look up", so PR polling reports no pull
        request rather than erroring.
        """
        checkout = location.checkout_path
        try:
            commit_id = self._read_working_copy_commit_id(checkout)
            projection = self._project_stack(checkout, commit_id, target_ref, requested_ref_name)
        except VcsCommandError as e:
            logger.debug("Cannot read the bookmarks of {}: {}", checkout, e)
            return PullRequestRefs(head_ref_names=())
        return PullRequestRefs(head_ref_names=projection.pr_head_candidates)

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
            _target_bookmark_name(target_ref),
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


def _stack_revset(working_copies: JjRevset, target_commit_id: str | None) -> JjRevset:
    """The working copies and their ancestors that are not the target's; without a target, their mutable ancestors."""
    if target_commit_id is None:
        return JjRevset(f"(::({working_copies}) & mutable()) | ({working_copies})")
    return JjRevset(f"(::({working_copies}) ~ ::{target_commit_id}) | ({working_copies})")


def _target_bookmark_name(target_ref: str | None) -> str | None:
    """The bookmark name in a target symbol, such as `main` for `main@origin`."""
    if target_ref is None:
        return None
    try:
        return parse_bookmark_symbol(target_ref).name
    except InvalidRevisionError:
        return None
