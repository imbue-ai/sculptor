import pytest

from imbue_core.pydantic_serialization import FrozenModel
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.auto_update_mock import mock_electron_api as mock_electron_api  # noqa: F401
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.task_starter import FAKE_PI_MODEL_NAME
from sculptor.testing.playwright_conftest import *  # noqa: F401, F403


@pytest.fixture(scope="session")
def sculptor_launch_mode(request: pytest.FixtureRequest) -> str:
    """Return the launch mode selected via ``--sculptor-launch-mode``."""
    return request.config.getoption("--sculptor-launch-mode", default="electron")


class HarnessTestConfig(FrozenModel):
    """The per-harness inputs needed by an integration test.

    Tests that parametrize over both harnesses read ``workspace_harness``
    to pick the value persisted on workspace creation, and ``model_name``
    for the chat-panel model picker.
    """

    workspace_harness: HarnessName
    model_name: str


_HARNESS_CONFIGS: dict[str, HarnessTestConfig] = {
    "claude": HarnessTestConfig(
        workspace_harness=HarnessName.CLAUDE,
        model_name=FAKE_CLAUDE_MODEL_NAME,
    ),
    "pi": HarnessTestConfig(
        workspace_harness=HarnessName.PI,
        model_name=FAKE_PI_MODEL_NAME,
    ),
}


@pytest.fixture
def harness(request: pytest.FixtureRequest) -> HarnessTestConfig:
    """Parametrized harness selector for tests that exercise both Claude and pi.

    Default value is ``"claude"`` so existing tests remain unaffected. Tests
    that need both harnesses parametrize indirectly::

        @pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
        def test_some_behavior(harness: HarnessTestConfig) -> None:
            ...
    """
    name = getattr(request, "param", "claude")
    if name not in _HARNESS_CONFIGS:
        raise ValueError(f"unknown harness param {name!r}; expected one of {sorted(_HARNESS_CONFIGS)}")
    return _HARNESS_CONFIGS[name]
