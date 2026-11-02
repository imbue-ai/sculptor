from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.workspace_service.api import CommitRecord

BranchDeletionPolicy = Literal["never", "delete_if_safe", "always"]
"""What `remove_checkout` does with the ref a workspace created; mirrors
`UserConfig.workspace_branch_deletion_policy`."""


class CheckoutSpec(FrozenModel):
    """What to create for a new workspace checkout."""

    repo_path: Path = Field(description="The user's repository the checkout is made from")
    checkout_path: Path = Field(description="Where the checkout's files go; in-place workspaces use repo_path")
    base_ref: str | None = Field(
        description="The ref the checkout starts from; None (clone only) uses the repository's current branch"
    )
    new_ref_name: str | None = Field(
        description="The ref created for the workspace; None (clone only) leaves the base checked out"
    )


class CheckoutLocation(FrozenModel):
    """Where an existing workspace checkout lives."""

    repo_path: Path = Field(description="The user's repository the checkout was made from")
    checkout_path: Path = Field(description="The directory holding the checkout's files")


class RefNameStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MALFORMED = "MALFORMED"
    ALREADY_EXISTS = "ALREADY_EXISTS"


class RefNameValidation(FrozenModel):
    """Whether a proposed name for a workspace's new ref can be used."""

    ref_name: str
    status: RefNameStatus


class GitHeadIdentity(FrozenModel):
    """Which branch a git checkout has checked out."""

    branch_name: str | None = Field(description="The checked-out branch; None when HEAD is detached")

    @property
    def is_detached(self) -> bool:
        return self.branch_name is None


class GitCommitHistory(FrozenModel):
    """The commits a git workspace has made since it forked from its target."""

    commits: list[CommitRecord] = Field(description="Newest first, capped at 500")
    fork_point: str | None = Field(description="The commit the history is measured from; None when unknown")


class RevisionDiff(FrozenModel):
    """The unified diff a single revision introduces."""

    diff: str = Field(description="Empty when the diff could not be produced")
    commit_id: str = Field(description="The full commit id of the revision")
    parent_commit_id: str | None = Field(description="None for a root commit")


class PullRequestRefs(FrozenModel):
    """What PR polling needs to find a workspace's pull request."""

    head_ref_names: tuple[str, ...] = Field(
        description="Candidate PR head names, most likely first; empty when there is nothing to look up"
    )
    origin_url: str | None = Field(description="The `origin` remote's URL; None when there is no origin")


class AgentVcsEnvironment(FrozenModel):
    """Additions to the environment of processes launched in a workspace."""

    path_prefixes: tuple[Path, ...] = Field(default=(), description="Directories prepended to PATH")
    environment_variables: dict[str, str] = Field(default_factory=dict)
