"""Tests for the manual test harness's sculptor-folder provisioning.

The harness must satisfy Sculptor's dependency gate for pi the same way the
pytest fixtures do: PI_VERSION_RANGE is an exact pin, so only a provisioned
pinned-version stub reliably passes the version check.
"""

import subprocess
from pathlib import Path

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.dependency_management_service import parse_pi_version
from sculptor.services.pi_version import PI_PINNED_VERSION
from sculptor.services.user_config.user_config import load_config
from sculptor.testing.manual_test_harness import _populate_sculptor_folder


def test_populate_sculptor_folder_pins_executable_pi_stub_in_config(tmp_path: Path) -> None:
    _populate_sculptor_folder(tmp_path)

    config = load_config(tmp_path / "internal" / "config.toml")
    pi_path = Path(config.dependency_paths.pi)

    assert pi_path.is_absolute()
    assert pi_path.is_file()
    assert pi_path.stat().st_mode & 0o111


def test_populate_sculptor_folder_pi_stub_passes_dependency_version_gate(tmp_path: Path) -> None:
    _populate_sculptor_folder(tmp_path)

    config = load_config(tmp_path / "internal" / "config.toml")
    result = subprocess.run(
        [config.dependency_paths.pi, "--version"], capture_output=True, text=True, check=False, timeout=30
    )

    assert result.returncode == 0
    # Real pi emits its version to stderr; the stub mirrors that.
    version = parse_pi_version(result.stderr)
    assert version == PI_PINNED_VERSION
    with ConcurrencyGroup(name="test") as cg:
        service = DependencyManagementService(concurrency_group=cg)
        assert service.is_version_in_range(version, Dependency.PI)
