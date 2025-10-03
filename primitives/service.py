from imbue_core.pydantic_serialization import MutableModel


class Service(MutableModel):
    def start(self) -> None:
        """
        Start the service and prepare it for use.

        Will be called during startup of the application.
        """

    def stop(self) -> None:
        """
        Close the service and release any resources it holds.

        Will be called and awaited during clean shutdown of the application.
        """
