import pytest

from sculptor.foundation.secrets_utils import Secret
from sculptor.services.workspace_service.vcs.runner_support import build_command_env
from sculptor.services.workspace_service.vcs.runner_support import read_no_env_overrides


def test_build_command_env_adds_nothing_without_overrides_or_extra_env() -> None:
    assert build_command_env(read_no_env_overrides, None) is None
    assert build_command_env(read_no_env_overrides, {}) is None


def test_build_command_env_unwraps_secrets_and_lets_extra_env_win_over_the_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCTEST_FROM_PROCESS", "process")

    env = build_command_env(
        lambda: {"SCTEST_SECRET": Secret("unwrapped"), "SCTEST_SHARED": "override"}, {"SCTEST_SHARED": "call"}
    )

    assert env is not None
    assert env["SCTEST_FROM_PROCESS"] == "process"
    assert env["SCTEST_SECRET"] == "unwrapped"
    assert env["SCTEST_SHARED"] == "call"
