from imbue_core.errors import ExpectedError


class LocalSyncError(ExpectedError):
    """Base exception for all local sync operations."""


class MutagenSyncError(LocalSyncError):
    """Exception raised when mutagen operations fail during sync."""

    def __init__(
        self,
        message: str,
        operation: str,
        session_name: str | None = None,
        sync_mode: str | None = None,
        source_path: str | None = None,
        dest_path: str | None = None,
        exit_code: int | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.session_name = session_name
        self.sync_mode = sync_mode
        self.source_path = source_path
        self.dest_path = dest_path
        self.exit_code = exit_code
        self.stderr = stderr

    def __str__(self) -> str:
        details = [super().__str__()]
        details.append(f"Operation: {self.operation}")
        if self.session_name:
            details.append(f"Session: {self.session_name}")
        if self.sync_mode:
            details.append(f"Sync mode: {self.sync_mode}")
        if self.source_path:
            details.append(f"Source: {self.source_path}")
        if self.dest_path:
            details.append(f"Destination: {self.dest_path}")
        if self.exit_code is not None:
            details.append(f"Exit code: {self.exit_code}")
        if self.stderr:
            details.append(f"Stderr: {self.stderr}")
        return "\n".join(details)
