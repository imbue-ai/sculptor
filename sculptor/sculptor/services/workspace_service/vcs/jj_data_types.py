from pathlib import Path

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel


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
