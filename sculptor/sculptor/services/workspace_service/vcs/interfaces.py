from abc import ABC
from abc import abstractmethod
from pathlib import Path

from sculptor.interfaces.agents.artifacts import DiffArtifact
from sculptor.services.workspace_service.api import FileAtRefResult
from sculptor.services.workspace_service.api import GitOperationResult
from sculptor.services.workspace_service.vcs.data_types import AgentVcsEnvironment
from sculptor.services.workspace_service.vcs.data_types import BranchDeletionPolicy
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.services.workspace_service.vcs.data_types import GitCommitHistory
from sculptor.services.workspace_service.vcs.data_types import GitHeadIdentity
from sculptor.services.workspace_service.vcs.data_types import PullRequestRefs
from sculptor.services.workspace_service.vcs.data_types import RefNameValidation
from sculptor.services.workspace_service.vcs.data_types import RevisionDiff
from sculptor.state.chat_state import ToolInput


class WorkspaceVcs(ABC):
    """Every version-control operation Sculptor performs on a workspace or its repository.

    One implementation per kind of workspace. Repository-scoped methods take the
    user's repository path; checkout-scoped methods take a `CheckoutLocation`.
    """

    @abstractmethod
    def create_checkout(self, spec: CheckoutSpec) -> CheckoutLocation:
        """Create the checkout a new workspace works in."""

    @abstractmethod
    def verify_checkout(self, location: CheckoutLocation) -> None:
        """Check that a resumed workspace's checkout is usable.

        Raises `EnvironmentNotFoundError` when it is not, so the caller re-creates it.
        """

    @abstractmethod
    def remove_checkout(
        self,
        location: CheckoutLocation,
        created_ref_name: str | None,
        deletion_policy: BranchDeletionPolicy,
    ) -> None:
        """Detach a deleted workspace's checkout from the repository and apply `deletion_policy` to its ref.

        Never raises: deleting a workspace must always make progress, so failures are logged.
        """

    @abstractmethod
    def resolve_default_target(self, repo_path: Path) -> str | None:
        """The ref a new workspace's changes are compared against when the user picks none."""

    @abstractmethod
    def list_target_candidates(self, repo_path: Path) -> list[str]:
        """Refs the user may choose as a workspace's target."""

    @abstractmethod
    def validate_new_ref_name(self, repo_path: Path, ref_name: str) -> RefNameValidation:
        """Whether `ref_name` can name the ref a new workspace creates."""

    @abstractmethod
    def resolve_base_commit_id(self, repo_path: Path, base_ref: str) -> str | None:
        """The commit id `base_ref` names, recorded as a new workspace's starting point; None if unresolvable."""

    @abstractmethod
    def default_setup_command(self) -> str:
        """The shell command run in a fresh checkout when the project configures none."""

    @abstractmethod
    def read_identity(self, location: CheckoutLocation) -> GitHeadIdentity:
        """What the checkout currently has checked out."""

    @abstractmethod
    def compute_diff_artifact(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        context_lines: int,
    ) -> DiffArtifact:
        """The uncommitted diff and, when `target_ref` is set, the diff against it."""

    @abstractmethod
    def get_revision_history(
        self,
        location: CheckoutLocation,
        target_ref: str | None,
        base_commit_id: str | None,
    ) -> GitCommitHistory:
        """The revisions the workspace has made since it forked from `target_ref`.

        `base_commit_id` is the fork point when there is no target or it cannot be resolved.
        """

    @abstractmethod
    def get_revision_diff(self, location: CheckoutLocation, commit_id: str) -> RevisionDiff:
        """The diff one revision introduces.

        Raises `InvalidRevisionError` when `commit_id` is malformed or names no commit.
        """

    @abstractmethod
    def list_files(self, location: CheckoutLocation) -> list[str]:
        """Every file in the checkout, relative to its root and sorted.

        Raises `CheckoutFilesUnavailableError` when the list cannot be produced right now.
        """

    @abstractmethod
    def read_file_at_revision(self, location: CheckoutLocation, file_path: str, revision: str) -> FileAtRefResult:
        """A file's content at `revision`.

        Raises `FileNotFoundAtRefError` when the file does not exist there.
        """

    @abstractmethod
    def discard_file_changes(self, location: CheckoutLocation, file_path: str) -> GitOperationResult:
        """Throw away the uncommitted changes to one file."""

    @abstractmethod
    def get_pull_request_refs(self, location: CheckoutLocation) -> PullRequestRefs:
        """What PR polling needs to look up the workspace's pull request."""

    @abstractmethod
    def agent_environment(self, location: CheckoutLocation) -> AgentVcsEnvironment:
        """Environment additions for agents, terminals and setup commands launched in the checkout."""

    @abstractmethod
    def compute_change_fingerprint(self, location: CheckoutLocation) -> str | None:
        """A value that changes whenever the checkout's content or history changes; None on failure."""


class TurnDiffTracker(ABC):
    """Tracks the files an agent changes during one turn."""

    @abstractmethod
    def rebaseline(self) -> None:
        """Start a new turn: later diffs and changed paths are measured from the checkout as it is now."""

    @abstractmethod
    def compute_diff_for_tool(self, tool_name: str, tool_input: ToolInput) -> str | None:
        """The diff a file-editing tool call made, or None when the tool edits no file."""

    @abstractmethod
    def get_changed_file_paths(self) -> list[str]:
        """Repository-relative paths of every file changed since the last rebaseline."""

    @abstractmethod
    def to_repo_relative_path(self, file_path: str) -> str:
        """`file_path` relative to the checkout root; paths outside it are returned unchanged."""
