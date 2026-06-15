from pathlib import Path

from pydantic import AnyUrl


class GitRepoError(Exception):
    """Exception raised when a git operation fails."""

    def __init__(
        self,
        message: str,
        operation: str,
        repo_url: AnyUrl | None = None,
        branch_name: str | None = None,
        exit_code: int | None = None,
        stderr: str | bytes | None = None,
    ) -> None:
        # The required positional constructor args prevent
        # SerializedException.build(e).construct_instance() from reconstructing this exception.
        super().__init__(message)
        self.operation = operation
        self.repo_url = repo_url
        self.branch_name = branch_name
        self.exit_code = exit_code
        self.stderr = stderr

    def __str__(self) -> str:
        details = [super().__str__()]
        details.append(f"Operation: {self.operation}")
        if self.repo_url:
            details.append(f"Repository: {self.repo_url}")
        if self.branch_name is not None:
            details.append(f"Branch: {self.branch_name}")
        if self.exit_code is not None:
            details.append(f"Exit code: {self.exit_code}")
        if self.stderr:
            details.append(f"Stderr: {self.stderr}")
        return "\n".join(details)


class GitRepoNotFoundError(GitRepoError):
    """Raised when the git repository path does not exist.

    A dedicated domain exception so callers can distinguish "repo is gone" from
    other git failures without catching the builtin ``FileNotFoundError`` (which
    the style guide forbids raising as a handled signal).
    """

    def __init__(self, repo_path: Path) -> None:
        super().__init__(
            message=f"Repository path does not exist: {repo_path}",
            operation="access_repository",
        )
