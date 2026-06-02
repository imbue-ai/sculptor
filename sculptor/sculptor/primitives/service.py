from contextlib import contextmanager
from contextlib import nullcontext
from typing import Generator

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import MutableModel
from sculptor.utils.timeout import log_runtime


class Service(MutableModel):
    concurrency_group: ConcurrencyGroup

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

    @contextmanager
    def run(self, log_runtimes: bool = False) -> Generator[None, None, None]:
        with self.concurrency_group as _concurrency_group:
            with log_runtime(f"SERVICES.start.{self.__class__.__name__}") if log_runtimes else nullcontext():
                self.start()
            try:
                yield
            finally:
                with log_runtime(f"SERVICES.stop.{self.__class__.__name__}") if log_runtimes else nullcontext():
                    self.stop()
