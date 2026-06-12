from imbue_core.errors import ExpectedError


class EnvironmentFailure(ExpectedError):
    """Errors related to environments."""


class EnvironmentNotFoundError(EnvironmentFailure):
    """Could not find (or start) an old environment."""


class EnvironmentConfigurationChangedError(EnvironmentFailure):
    """When the configuration has changed, we can no longer start the previous Environment."""


class FileNotFoundEnvironmentError(EnvironmentFailure, FileNotFoundError):
    """Error raised when a file is not found."""


class FileOrDirectoryCouldNotBeDeletedError(EnvironmentFailure, OSError):
    """Error raised when a file or directory could not be deleted."""
