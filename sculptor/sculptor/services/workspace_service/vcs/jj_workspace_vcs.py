"""Version control for jj workspaces: jj-only checkouts (`.jj` and no `.git`) of a colocated repository.

Reads that only look at recorded history pass `IGNORE_WORKING_COPY`, so they
add no operation. Reads that must see the agent's edits snapshot once, read the
working-copy commit id, and pin every follow-up read to that commit. A
snapshotting read in a stale workspace raises `JjWorkingCopyStaleError`, unless
the interface gives the method a failure value of its own.
"""

from collections.abc import Callable
from pathlib import Path

from loguru import logger

from sculptor.interfaces.environments.errors import EnvironmentNotFoundError
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import RefNameStatus
from sculptor.services.workspace_service.vcs.data_types import RefNameValidation
from sculptor.services.workspace_service.vcs.errors import InvalidCheckoutSpecError
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_repo_queries import does_ref_exist
from sculptor.services.workspace_service.vcs.git_repo_queries import is_well_formed_branch_name
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmarkSymbol
from sculptor.services.workspace_service.vcs.jj_repo_queries import add_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import does_bookmark_exist
from sculptor.services.workspace_service.vcs.jj_repo_queries import forget_workspace
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_bookmarks
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_workspaces
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_commit_id
from sculptor.services.workspace_service.vcs.jj_repo_queries import resolve_trunk_symbol
from sculptor.services.workspace_service.vcs.jj_repo_queries import set_workspace_config
from sculptor.services.workspace_service.vcs.jj_revsets import format_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import revset_for_base

# Fetches the origin remote if present, and succeeds silently when there is no
# origin, so workspace startup is never blocked on it.
DEFAULT_JJ_WORKSPACE_SETUP_COMMAND = "jj git fetch --remote origin 2>/dev/null || true"

# Returns the user's configured limit, in MiB, on the size of a new file jj snapshots.
SnapshotSizeLimitReader = Callable[[], int]

_SNAPSHOT_MAX_NEW_FILE_SIZE_KEY = "snapshot.max-new-file-size"
_BYTES_PER_MEBIBYTE = 1024 * 1024
_STORE_LINK = Path(".jj") / "repo"


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
