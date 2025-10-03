from typing import Sequence

from imbue_core.errors import ExpectedError


class GitCommandFailure(ExpectedError):
    def __init__(self, message: str, command: Sequence[str], returncode: int | None, stdout: str, stderr: str) -> None:
        """Initialize this error.

        Args:
                message: The text of this error message.
                command: The git command that was run.
                returncode: The return code of the git command. This may be None if the command could not be run.
                stdout: The standard output of the git command.
                stderr: The standard error of the git command.
        """
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(message)

    @property
    def is_transient(self) -> bool:
        return _is_transient_git_error(self.returncode, self.stderr)


class RetriableGitCommandFailure(GitCommandFailure):
    pass


def _is_transient_git_error(returncode: int | None, stderr: str) -> bool:
    # TODO: let's implement this later as we figure out what errors are transient (using sentry for example)
    # it should be safe to retry even if the error is not transient since we only retry idempotent commands
    return True
