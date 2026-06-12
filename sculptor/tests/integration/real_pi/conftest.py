"""Configuration for real pi integration tests.

These tests run against a real ``pi`` CLI (not FakePi) and require:

- The pinned ``pi`` binary installed in the workspace venv via
  ``just install-pi`` (see ``PI_VERSION_RANGE`` in
  ``dependency_management_service``).
- A valid ``ANTHROPIC_API_KEY`` in the environment.

They are marked with ``@pytest.mark.real_pi`` and run via ``just test-real-pi``
(excluded from CI; cost API credits).
"""

from typing import Any

import pytest

import sculptor.testing.resources as resources_mod
import sculptor.testing.server_utils as server_utils_mod
from sculptor.testing.auto_update_mock import mock_electron_api as mock_electron_api  # noqa: F401
from sculptor.testing.dependency_stubs import disable_default_pi_stub_for_session
from sculptor.testing.playwright_conftest import *  # noqa: F401, F403
from sculptor.testing.resources import invalidate_shared_instance


@pytest.fixture(scope="session")
def sculptor_launch_mode(request: pytest.FixtureRequest) -> str:
    """Return the launch mode selected via ``--sculptor-launch-mode``."""
    return request.config.getoption("--sculptor-launch-mode", default="electron")


@pytest.fixture(autouse=True, scope="session")
def _expose_api_keys_for_real_pi(request: pytest.FixtureRequest) -> None:
    """Override the testing environment to use real API keys and the real pi CLI.

    Monkeypatches ``get_testing_environment`` so the shared SculptorInstance
    receives the real ``ANTHROPIC_API_KEY`` (which pi reads via the default
    ``PiConfig.api_key_env_var_names``), skips the default pi stub install so
    ``DependencyPaths.pi`` resolves the pinned binary in the workspace venv,
    and invalidates the cached shared instance so it picks both up.
    """
    _original_get_testing_environment = server_utils_mod.get_testing_environment

    def _get_testing_environment_with_real_keys(*args: Any, **kwargs: Any) -> dict[str, str | None]:
        # Force real API keys (so pi sees ANTHROPIC_API_KEY / falls back to its
        # auth.json). Forward *args/**kwargs verbatim rather than re-declaring the
        # signature: the shared-instance and restart-factory call paths pass
        # different arities, and this stays correct across future changes to
        # get_testing_environment's signature.
        kwargs["hide_keys"] = False
        return _original_get_testing_environment(*args, **kwargs)

    server_utils_mod.get_testing_environment = _get_testing_environment_with_real_keys
    resources_mod.get_testing_environment = _get_testing_environment_with_real_keys

    disable_default_pi_stub_for_session()

    invalidate_shared_instance(request.config)
