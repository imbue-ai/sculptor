"""Terminal manager abstract base class for Sculptor environments."""

import abc


class TerminalManager(abc.ABC):
    """Abstract base class for terminal managers.

    Terminal managers handle terminal session lifecycle:
    - Creating and managing terminal sessions
    - Providing cleanup when sessions terminate
    """

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop the terminal session and clean up resources.

        This method should:
        - Terminate any terminal server processes
        - Kill any terminal sessions
        - Clean up any temporary files or configurations
        """
        ...
