"""Configuration for real Claude integration tests.

These tests run against the real Claude CLI (not FakeClaude). They require:
- A real `claude` CLI binary installed and on PATH
- The CLI to be logged in (run ``claude /login`` once to write OAuth
  credentials to ``~/.claude/``). The conftest just stops Sculptor from
  injecting the fake ``sk-HIDDEN-FOR-TESTING`` value so the CLI's normal
  OAuth flow is what authenticates the request.

They are marked with @real_claude and should be run separately from the
regular integration test suite (they are slow and consume Claude usage).

Run with:
    just test-real-claude sculptor/tests/integration/real_claude/
"""

from pathlib import Path

import pytest

import sculptor.testing.resources as resources_mod
import sculptor.testing.server_utils as server_utils_mod
from sculptor.testing.auto_update_mock import mock_electron_api as mock_electron_api  # noqa: F401
from sculptor.testing.dependency_stubs import disable_default_claude_stub_for_session
from sculptor.testing.playwright_conftest import *  # noqa: F401, F403
from sculptor.testing.resources import invalidate_shared_instance


@pytest.fixture(scope="session")
def sculptor_launch_mode(request: pytest.FixtureRequest) -> str:
    """Return the launch mode selected via ``--sculptor-launch-mode``."""
    return request.config.getoption("--sculptor-launch-mode", default="electron")


@pytest.fixture(autouse=True, scope="session")
def _expose_real_claude_credentials(request: pytest.FixtureRequest) -> None:
    """Let the Claude CLI use its real OAuth credentials instead of the test stub.

    The default test environment forces ``ANTHROPIC_API_KEY="sk-HIDDEN-FOR-TESTING"``,
    which would actively block Claude CLI from reaching its OAuth credentials
    at ``~/.claude/``. Passing ``hide_keys=False`` here removes that override
    so the CLI's normal OAuth flow handles auth.

    (``hide_keys=False`` also forwards a real ``ANTHROPIC_API_KEY`` /
    ``~/.anthropic_api_key`` to the backend if either happens to be set,
    but OAuth is the path the team actually uses.)

    This monkeypatches get_testing_environment at session scope so the shared
    SculptorInstance created by sculptor_instance_ inherits the change.
    """
    _original_get_testing_environment = server_utils_mod.get_testing_environment

    def _get_testing_environment_with_real_keys(
        database_url: str,
        sculptor_folder: Path,
        tmp_path: Path,
        static_files_path: Path,
        hide_keys: bool = True,
    ) -> dict[str, str | None]:
        return _original_get_testing_environment(
            database_url=database_url,
            sculptor_folder=sculptor_folder,
            tmp_path=tmp_path,
            static_files_path=static_files_path,
            hide_keys=False,
        )

    # Patch both the module and the resources module's imported reference
    server_utils_mod.get_testing_environment = _get_testing_environment_with_real_keys
    resources_mod.get_testing_environment = _get_testing_environment_with_real_keys

    # Skip the default claude stub install. real_claude tests need the actual
    # CLI; without this, the shared instance pins ``DependencyPaths.claude`` to
    # the stub binary at ``fake_bin/claude`` and every agent invocation fails
    # with ``stub_error: Claude stub: not a real installation``.
    disable_default_claude_stub_for_session()

    # Invalidate any cached shared instance so it gets recreated with real keys
    # and the real claude binary path
    invalidate_shared_instance(request.config)
