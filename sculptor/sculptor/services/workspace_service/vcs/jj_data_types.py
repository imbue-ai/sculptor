from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel


class JjBookmarkSymbol(FrozenModel):
    """A bookmark as jj names it on the command line: `main` locally, `main@origin` on a remote."""

    name: str
    remote: str | None = Field(description="None for a local bookmark")
