from types import TracebackType

import pytest

user_story = pytest.mark.user_story


class UserStoryExpectation:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __enter__(self) -> None:
        print(f"Checking expectation: {self.tag}")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            print(f"Expectation failed: {self.tag}")
        else:
            print(f"Expectation passed: {self.tag}")
