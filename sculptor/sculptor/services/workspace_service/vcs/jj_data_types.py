from pathlib import Path

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.workspace_service.vcs.data_types import CommitFileChange


class JjBookmarkSymbol(FrozenModel):
    """A bookmark as jj names it on the command line: `main` locally, `main@origin` on a remote."""

    name: str
    remote: str | None = Field(description="None for a local bookmark")


class JjBookmark(FrozenModel):
    """One local or remote bookmark, as `jj bookmark list --all-remotes` reports it."""

    name: str
    remote: str | None = Field(description="None for a local bookmark")
    target_commit_ids: tuple[str | None, ...] = Field(
        description="One commit id normally; every side of a conflict when conflicted; None for an absent side"
    )
    is_tracked: bool = Field(description="Whether a local bookmark tracks this remote bookmark; False for a local one")

    @property
    def is_conflicted(self) -> bool:
        return len(self.target_commit_ids) > 1

    @property
    def commit_id(self) -> str | None:
        """The commit the bookmark points at; None when it is conflicted or absent.

        A local bookmark is absent after `jj bookmark delete` while a remote
        bookmark still tracks it.
        """
        if self.is_conflicted:
            return None
        return self.target_commit_ids[0]


class JjWorkspaceEntry(FrozenModel):
    """A workspace the repository records, as `jj workspace list` reports it."""

    name: str
    root: Path = Field(description="Absolute")


class JjStackRevision(FrozenModel):
    """One revision of a workspace's stack, as the stack projection needs it."""

    commit_id: str
    parent_commit_ids: tuple[str, ...]
    bookmarks: tuple[str, ...] = Field(description="The local bookmarks on this revision; conflicted ones excluded")
    is_described: bool = Field(description="Whether the revision has a non-empty description")


class JjStackProjection(FrozenModel):
    """What a workspace's stack says about its bookmarks."""

    bookmarks: tuple[str, ...] = Field(description="Every local bookmark on the stack, nearest the working copy first")
    pr_head_candidates: tuple[str, ...] = Field(
        description="The bookmarks a pull request may be headed by, most likely first; never the target's own name"
    )
    unbookmarked_revision_count: int = Field(
        description="Described revisions above the primary bookmark; every described revision when there is none"
    )

    @property
    def primary_bookmark(self) -> str | None:
        """The bookmark that names the workspace's work, or None when the stack has none."""
        if not self.pr_head_candidates:
            return None
        return self.pr_head_candidates[0]


class JjHeadIdentity(FrozenModel):
    """What a jj workspace's working copy is, and which bookmarks name its stack."""

    working_copy_change_id: str
    working_copy_change_id_prefix: str = Field(description="The shortest prefix that identifies the change uniquely")
    description_first_line: str = Field(description="Empty when the working copy has no description")
    is_working_copy_empty: bool
    bookmarks: tuple[str, ...] = Field(description="The local bookmarks on the stack, nearest the working copy first")
    primary_bookmark: str | None
    unbookmarked_revision_count: int = Field(
        description="Described revisions above the primary bookmark; every described revision when there is none"
    )
    has_conflict: bool = Field(description="Whether the working copy has unresolved conflicts")
    is_divergent: bool = Field(description="Whether the working copy's change has more than one visible commit")


class JjWorkingCopySnapshot(FrozenModel):
    """A workspace's working-copy commit as a snapshot just left it."""

    commit_id: str
    parent_commit_ids: tuple[str, ...]
    refused_files: dict[str, str] = Field(
        description="Files jj refused to snapshot, relative to the workspace root, each mapped to jj's reason"
    )

    @property
    def sole_parent_commit_id(self) -> str | None:
        """The commit the working copy's own changes are measured from; None for a merge."""
        if len(self.parent_commit_ids) != 1:
            return None
        return self.parent_commit_ids[0]


class JjRevisionRecord(FrozenModel):
    """One revision in a jj workspace's history."""

    change_id: str
    commit_id: str
    description: str = Field(description="The whole description, without jj's trailing newline")
    author_name: str
    author_email: str
    timestamp: str = Field(description="When the author made the change, in ISO 8601 with a UTC offset")
    parent_commit_ids: tuple[str, ...]
    bookmarks: tuple[str, ...] = Field(description="The local bookmarks on this revision")
    files: tuple[CommitFileChange, ...]
    is_empty: bool
    has_conflict: bool
    is_divergent: bool
    is_working_copy: bool = Field(description="Whether this is the workspace's own working-copy commit")


class JjRevisionHistory(FrozenModel):
    """The revisions a jj workspace has made since it forked from its target."""

    revisions: tuple[JjRevisionRecord, ...] = Field(description="Newest first, truncated to a fixed maximum")
    fork_point: str | None = Field(description="The commit the history is measured from; None when there is none")
