from pathlib import Path
from typing import Sequence

from sculptor.foundation.errors import ExpectedError


class VcsCommandError(ExpectedError):
    """A version-control command (git, gh or jj) could not be started, exited non-zero, or timed out."""

    def __init__(
        self,
        message: str,
        command: Sequence[str],
        returncode: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        self.command = tuple(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(message)


class VcsCommandExitError(VcsCommandError):
    """A version-control command ran to completion and exited non-zero."""


class JjWorkingCopyStaleError(VcsCommandExitError):
    """A jj command failed because the workspace's working copy is stale relative to its repository.

    Raised whether or not the command was checked: a stale workspace is not an
    ordinary failure, because every command that snapshots it fails until
    `jj workspace update-stale` runs, while reads that ignore the working copy
    keep working.
    """


class VcsCommandTimeoutError(VcsCommandError):
    """A version-control command ran past its timeout."""


class VcsBinaryNotFoundError(VcsCommandError):
    """The configured binary for a version-control tool cannot be resolved."""


class InvalidRevisionError(ValueError):
    """A revision argument is malformed or does not name a commit."""


class CheckoutFilesUnavailableError(ExpectedError):
    """The checkout's file list cannot be produced right now.

    Distinguishes a transient failure (e.g. lock contention while another
    process writes the index) from a checkout that legitimately has no files.
    """

    def __init__(self, checkout_path: Path, detail: str) -> None:
        self.checkout_path = checkout_path
        super().__init__(f"Files unavailable for checkout {checkout_path}: {detail}")


class GitCommandInJjWorkspaceError(Exception):
    """Sculptor tried to run git inside a jj workspace, which has `.jj` and no `.git`.

    Deliberately outside the `VcsCommandError` family: call sites that degrade
    gracefully on git failures must not swallow this, because in a jj workspace
    git would otherwise fail on every call and the feature would go quietly dark.
    """

    def __init__(self, command: Sequence[str], cwd: Path, workspace_root: Path) -> None:
        self.command = tuple(command)
        self.cwd = cwd
        self.workspace_root = workspace_root
        super().__init__(f"Refusing to run {' '.join(command)!r} in {cwd}: {workspace_root} is a jj workspace")


class InvalidCheckoutSpecError(ValueError):
    """A `CheckoutSpec` lacks a field the workspace kind requires."""
