"""jj as an optional managed dependency, and the JJ_AVAILABLE readiness derived from it.

These tests run the real jj binary, or stub scripts that print a chosen ``--version``,
against a throwaway Sculptor data folder and a PATH holding only what each test puts there.
"""

import hashlib
import http.server
import io
import shutil
import tarfile
import threading
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from queue import Queue
from uuid import uuid4

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.dependency_management_service import Dependency
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.dependency_management_service import JjIdentityError
from sculptor.services.dependency_management_service import _configured_binary_value
from sculptor.services.jj_version import JJ_MINIMUM_GIT_VERSION
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.services.managed_tools import JjManagedTool
from sculptor.services.managed_tools import ResolvedDistribution
from sculptor.services.managed_tools import get_managed_tools
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG
from sculptor.utils.build import get_sculptor_folder
from sculptor.web.data_types import BinaryMode
from sculptor.web.data_types import BinarySource
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjNotRunnable
from sculptor.web.data_types import JjShadowed
from sculptor.web.data_types import JjUnsupportedGit
from sculptor.web.data_types import JjUnsupportedVersion
from sculptor.web.data_types import LoginShellJj


class _JjTestHome(FrozenModel):
    """Where a test puts binaries (the only PATH entry) and Sculptor's data."""

    bin_dir: Path
    sculptor_folder: Path

    @property
    def managed_jj_dir(self) -> Path:
        return self.sculptor_folder / "internal" / "dependencies" / "jj"

    def write_stub(self, name: str, script_body: str) -> Path:
        stub = self.bin_dir / name
        stub.write_text(f"#!/bin/bash\n{script_body}\n")
        stub.chmod(0o755)
        return stub


@pytest.fixture
def jj_test_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, jj_isolated_env: JjIsolatedEnv
) -> Iterator[_JjTestHome]:
    git_binary = shutil.which("git")
    assert git_binary is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(git_binary)
    sculptor_folder = tmp_path / "sculptor"
    sculptor_folder.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv(SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG, str(sculptor_folder))
    get_sculptor_folder.cache_clear()
    yield _JjTestHome(bin_dir=bin_dir, sculptor_folder=sculptor_folder)
    get_sculptor_folder.cache_clear()
    set_user_config_instance(None)


@pytest.fixture
def jj_service() -> Iterator[DependencyManagementService]:
    with ConcurrencyGroup(name="dependency_management_service") as concurrency_group:
        yield DependencyManagementService(concurrency_group=concurrency_group)


def _jj_user_config(jj_value: str, git: str | None = None) -> UserConfig:
    return UserConfig(
        user_email="test@example.com",
        user_id=uuid4().hex,
        organization_id=uuid4().hex,
        instance_id=uuid4().hex,
        dependency_paths=DependencyPaths(git=git, claude="claude", pi="pi", jj=jj_value),
    )


def _configure_jj(jj_value: str, git: str | None = None) -> None:
    set_user_config_instance(_jj_user_config(jj_value, git))


def _stage_managed_jj(home: _JjTestHome, version: str, target: Path) -> Path:
    staged = home.managed_jj_dir / f"version-{version}" / "jj"
    staged.parent.mkdir(parents=True)
    staged.symlink_to(target)
    return staged


def _old_jj_stub(home: _JjTestHome) -> Path:
    return home.write_stub("jj", f'echo "jj 0.45.0-{uuid4().hex}"')


def test_jj_defaults_to_managed_mode() -> None:
    assert DependencyPaths().jj == "MANAGED"


def test_jj_snapshot_size_limit_defaults_to_ten_mebibytes() -> None:
    config = UserConfig(user_email="", user_id=uuid4().hex, organization_id=uuid4().hex, instance_id=uuid4().hex)
    assert config.jj_snapshot_max_new_file_size_mib == 10


def test_every_managed_tool_has_a_configured_binary_value() -> None:
    config = _jj_user_config("/opt/jj")

    values = {tool: _configured_binary_value(config, tool) for tool in get_managed_tools()}

    assert values == {Dependency.CLAUDE: "claude", Dependency.PI: "pi", Dependency.JJ: "/opt/jj"}


def test_jj_version_range_accepts_the_pin_and_later_zero_x_releases(jj_service: DependencyManagementService) -> None:
    assert jj_service.is_version_in_range(JJ_PINNED_VERSION, Dependency.JJ) is True
    assert jj_service.is_version_in_range("0.47.3", Dependency.JJ) is True
    assert jj_service.is_version_in_range("0.45.9", Dependency.JJ) is False
    assert jj_service.is_version_in_range("1.0.0", Dependency.JJ) is False


def test_jj_custom_mode_with_no_path_is_not_installed(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    _configure_jj("CUSTOM")

    status = jj_service.get_status()

    assert jj_service.resolve_binary_path(Dependency.JJ) is None
    assert status.jj.installed is False
    assert status.jj.mode == BinaryMode.CUSTOM
    assert status.jj_readiness == JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED)


def test_jj_managed_mode_without_a_download_falls_back_to_jj_on_path(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    path_jj = jj_test_home.bin_dir / "jj"
    path_jj.symlink_to(jj_binary.path)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.jj.path == str(path_jj)
    assert status.jj.mode == BinaryMode.MANAGED
    assert status.jj.source == BinarySource.EXTERNAL
    assert status.jj.version == jj_binary.version
    assert status.jj.is_version_in_range is True
    assert status.jj.managed_version is None
    assert status.jj_readiness == JjAvailable(
        blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)
    )


def test_jj_managed_mode_prefers_the_downloaded_copy(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    _old_jj_stub(jj_test_home)
    staged = _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.jj.path == str(staged)
    assert status.jj.source == BinarySource.MANAGED
    assert status.jj.managed_version == JJ_PINNED_VERSION
    assert isinstance(status.jj_readiness, JjAvailable)


def test_jj_custom_path_resolves_the_configured_binary(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    _configure_jj(str(jj_binary.path))

    status = jj_service.get_status()

    assert status.jj.path == str(jj_binary.path)
    assert status.jj.mode == BinaryMode.CUSTOM
    assert status.jj.source == BinarySource.EXTERNAL
    assert isinstance(status.jj_readiness, JjAvailable)


def test_jj_that_fails_to_run_is_not_runnable_with_the_first_stderr_line(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
) -> None:
    jj_isolated_env.jj_config_path.write_text("garbage = =\n")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjNotRunnable(
        blocker=JjBlocker.NOT_RUNNABLE, error="Config error: Configuration cannot be parsed as TOML document"
    )


def test_an_old_jj_is_unsupported_and_reports_its_path_and_version(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    stub = _old_jj_stub(jj_test_home)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.jj.is_version_in_range is False
    assert status.jj_readiness == JjUnsupportedVersion(
        blocker=JjBlocker.UNSUPPORTED_VERSION, path=str(stub), version="0.45.0"
    )


def test_a_jj_with_unrecognized_version_output_is_unsupported(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    stub = jj_test_home.write_stub("jj", 'echo "jujutsu nightly"')
    _configure_jj("MANAGED")

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjUnsupportedVersion(blocker=JjBlocker.UNSUPPORTED_VERSION, path=str(stub), version=None)


def test_jj_without_an_identity_suggests_the_global_git_identity(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjNoIdentity(
        blocker=JjBlocker.NO_IDENTITY,
        suggested_identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL),
    )


def test_jj_with_half_an_identity_keeps_its_own_half_in_the_suggestion(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JJ_USER", "Ada Lovelace")
    monkeypatch.delenv("JJ_EMAIL")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjNoIdentity(
        blocker=JjBlocker.NO_IDENTITY, suggested_identity=JjIdentity(name="Ada Lovelace", email=JJ_TEST_USER_EMAIL)
    )


def test_jj_identity_set_in_the_sculptor_env_file_counts(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")
    (jj_test_home.sculptor_folder / ".env").write_text("JJ_USER=Env File User\nJJ_EMAIL=env-file@example.com\n")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjAvailable(
        blocker=None, identity=JjIdentity(name="Env File User", email="env-file@example.com")
    )


def test_setting_the_jj_identity_writes_the_user_config_and_makes_jj_available(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")
    _configure_jj(str(jj_binary.path))
    identity = JjIdentity(name="Grace Hopper", email="grace@example.com")

    status = jj_service.set_jj_identity(identity)

    assert status.jj_readiness == JjAvailable(blocker=None, identity=identity)
    assert "Grace Hopper" in jj_isolated_env.jj_config_path.read_text()


def test_setting_the_jj_identity_without_jj_raises(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    _configure_jj("CUSTOM")

    with pytest.raises(JjIdentityError):
        jj_service.set_jj_identity(JjIdentity(name="Grace Hopper", email="grace@example.com"))


def test_check_installed_keeps_the_first_stderr_line_of_a_failing_version_probe(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    stub = jj_test_home.write_stub("jj", 'echo "first problem" >&2\necho "second problem" >&2\nexit 1')
    _configure_jj("MANAGED")

    check = jj_service.check_installed(Dependency.JJ)

    assert check.installed is False
    assert check.path == str(stub)
    assert check.probe_error == "first problem"


def test_check_installed_falls_back_to_the_error_message_when_stderr_is_empty(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    jj_test_home.write_stub("jj", "exit 1")
    _configure_jj("MANAGED")

    check = jj_service.check_installed(Dependency.JJ)

    assert check.probe_error == "Command failed with non-zero exit code"


def test_a_jj_whose_identity_probe_fails_is_not_runnable_with_the_first_stderr_line(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    jj_test_home.write_stub(
        "jj",
        f'if [ "$1" = --version ]; then echo "jj {JJ_PINNED_VERSION}-{uuid4().hex}"; exit 0; fi\n'
        + 'echo "Config error: unreadable user config" >&2\necho "more detail" >&2\nexit 1',
    )
    _configure_jj("MANAGED")

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjNotRunnable(blocker=JjBlocker.NOT_RUNNABLE, error="Config error: unreadable user config")


def test_setting_the_jj_identity_reports_the_first_stderr_line_of_a_failed_write(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    jj_test_home.write_stub("jj", 'echo "Config error: read-only config" >&2\necho "more detail" >&2\nexit 1')
    _configure_jj("MANAGED")

    with pytest.raises(JjIdentityError, match="^Config error: read-only config$"):
        jj_service.set_jj_identity(JjIdentity(name="Grace Hopper", email="grace@example.com"))


def test_check_installed_reads_a_version_printed_on_stderr_for_any_tool(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    stub = jj_test_home.write_stub("stderr-git", 'echo "git version 2.44.0" >&2')
    _configure_jj("CUSTOM", git=str(stub))

    check = jj_service.check_installed(Dependency.GIT)

    assert check.version == "2.44.0"


@pytest.mark.allow_dependency_downloads
def test_startup_never_downloads_jj_when_no_managed_copy_exists(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    (jj_test_home.bin_dir / "jj").symlink_to(jj_binary.path)
    _configure_jj("MANAGED")

    jj_service._auto_install_if_needed()

    assert jj_service._install_thread == {}


def _jj_stub_in(directory: Path, version_output: str) -> Path:
    directory.mkdir()
    stub = directory / "jj"
    stub.write_text(f'#!/bin/bash\necho "{version_output}"\n')
    stub.chmod(0o755)
    return stub


def _make_login_profile_put_first(
    directory: Path, jj_isolated_env: JjIsolatedEnv, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Make the user's login shell bash, with a profile that puts `directory` first on PATH and logs each run to the returned file.

    The profile also prints a greeting, as many do, so the tests show the probe is not misled by what a profile prints.
    """
    runs_log = jj_isolated_env.home_path / "profile_runs.log"
    monkeypatch.setenv("SHELL", "/bin/bash")
    (jj_isolated_env.home_path / ".bash_profile").write_text(
        f'echo "Welcome back!"\necho ran >> "{runs_log}"\nexport PATH="{directory}:$PATH"\n'
    )
    return runs_log


def test_jj_is_unavailable_while_the_login_shell_runs_an_older_jj_instead_of_sculptors(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    cargo_jj = _jj_stub_in(tmp_path / "cargo_bin", f"jj 0.28.2-{uuid4().hex}")
    _make_login_profile_put_first(cargo_jj.parent, jj_isolated_env, monkeypatch)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.login_shell_jj == LoginShellJj(path=str(cargo_jj), version="0.28.2", is_version_in_range=False)
    assert status.jj_readiness == JjShadowed(blocker=JjBlocker.SHADOWED, path=str(cargo_jj), version="0.28.2")


def test_a_supported_jj_the_login_shell_runs_instead_of_sculptors_is_reported_without_blocking_jj(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    homebrew_jj = _jj_stub_in(tmp_path / "homebrew_bin", "jj 0.99.0")
    _make_login_profile_put_first(homebrew_jj.parent, jj_isolated_env, monkeypatch)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.login_shell_jj == LoginShellJj(path=str(homebrew_jj), version="0.99.0", is_version_in_range=True)
    assert status.jj_readiness == JjAvailable(
        blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)
    )


def test_readiness_is_unchanged_when_the_login_shell_finds_no_other_jj(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    directory_without_jj = tmp_path / "tools"
    directory_without_jj.mkdir()
    _make_login_profile_put_first(directory_without_jj, jj_isolated_env, monkeypatch)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.login_shell_jj is None
    assert status.jj_readiness == JjAvailable(
        blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)
    )


def test_the_login_shell_is_asked_with_the_term_a_workspace_terminal_gives_it(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    cargo_jj = _jj_stub_in(tmp_path / "cargo_bin", "jj 0.28.2")
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("TERM", "dumb")
    (jj_isolated_env.home_path / ".bash_profile").write_text(
        f'[ "$TERM" = dumb ] && return\nexport PATH="{cargo_jj.parent}:$PATH"\n'
    )
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.jj_readiness == JjShadowed(blocker=JjBlocker.SHADOWED, path=str(cargo_jj), version="0.28.2")


def test_the_login_shell_is_first_asked_once_jj_is_otherwise_ready(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    cargo_jj = _jj_stub_in(tmp_path / "cargo_bin", "jj 0.28.2")
    profile_runs_log = _make_login_profile_put_first(cargo_jj.parent, jj_isolated_env, monkeypatch)
    _configure_jj("MANAGED")
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")
    status_without_an_identity = jj_service.get_status()
    has_asked_the_shell_without_an_identity = profile_runs_log.exists()
    monkeypatch.setenv("JJ_USER", JJ_TEST_USER_NAME)
    monkeypatch.setenv("JJ_EMAIL", JJ_TEST_USER_EMAIL)

    status_with_an_identity = jj_service.refresh_status()

    assert isinstance(status_without_an_identity.jj_readiness, JjNoIdentity)
    assert has_asked_the_shell_without_an_identity is False
    assert status_with_an_identity.jj_readiness == JjShadowed(
        blocker=JjBlocker.SHADOWED, path=str(cargo_jj), version="0.28.2"
    )


def test_a_gate_reads_the_login_shell_jj_of_the_last_computed_status_without_starting_a_shell(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    cargo_jj = _jj_stub_in(tmp_path / "cargo_bin", "jj 0.28.2")
    profile_runs_log = _make_login_profile_put_first(cargo_jj.parent, jj_isolated_env, monkeypatch)
    _configure_jj("MANAGED")

    readiness_before_any_status = jj_service.probe_jj_readiness()
    jj_service.get_status()
    readiness_after_the_status = jj_service.probe_jj_readiness()

    assert isinstance(readiness_before_any_status, JjAvailable)
    assert readiness_after_the_status == JjShadowed(blocker=JjBlocker.SHADOWED, path=str(cargo_jj), version="0.28.2")
    assert profile_runs_log.read_text().splitlines() == ["ran"]


def _git_stub_in(directory: Path, version: str) -> Path:
    """A `git` in `directory` that reports `version` as Apple's Command Line Tools git does."""
    directory.mkdir(exist_ok=True)
    stub = directory / "git"
    stub.unlink(missing_ok=True)
    stub.write_text(f'#!/bin/bash\necho "git version {version} (Apple Git-154)"\n')
    stub.chmod(0o755)
    return stub


def _set_jj_git_executable_path(jj_isolated_env: JjIsolatedEnv, git: Path) -> None:
    jj_isolated_env.jj_config_path.write_text(f'[git]\nexecutable-path = "{git}"\n')


def test_jj_is_unavailable_while_the_git_first_on_path_is_older_than_jj_accepts(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    old_git = _git_stub_in(jj_test_home.bin_dir, "2.39.5")
    _stage_managed_jj(jj_test_home, JJ_PINNED_VERSION, jj_binary.path)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.jj_readiness == JjUnsupportedGit(
        blocker=JjBlocker.UNSUPPORTED_GIT, path=str(old_git), version="2.39.5", minimum_version=JJ_MINIMUM_GIT_VERSION
    )


def test_jj_is_unavailable_while_its_git_executable_path_names_a_git_older_than_it_accepts(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
) -> None:
    old_git = _git_stub_in(tmp_path / "old_git", "2.39.5")
    _set_jj_git_executable_path(jj_isolated_env, old_git)
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjUnsupportedGit(
        blocker=JjBlocker.UNSUPPORTED_GIT, path=str(old_git), version="2.39.5", minimum_version=JJ_MINIMUM_GIT_VERSION
    )


def test_jj_is_unavailable_while_its_git_executable_path_names_no_git(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
    tmp_path: Path,
) -> None:
    _set_jj_git_executable_path(jj_isolated_env, tmp_path / "missing" / "git")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjUnsupportedGit(
        blocker=JjBlocker.UNSUPPORTED_GIT, path=None, version=None, minimum_version=JJ_MINIMUM_GIT_VERSION
    )


def test_readiness_is_unchanged_by_a_git_at_the_oldest_version_jj_accepts(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    _git_stub_in(jj_test_home.bin_dir, JJ_MINIMUM_GIT_VERSION)
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness == JjAvailable(
        blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)
    )


def test_a_git_too_old_for_jj_is_reported_before_a_missing_identity(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")
    _git_stub_in(jj_test_home.bin_dir, "2.39.5")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness.blocker == JjBlocker.UNSUPPORTED_GIT


def test_a_gate_finds_a_git_too_old_for_jj_that_came_first_on_path_after_the_last_status(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    _configure_jj(str(jj_binary.path))
    status = jj_service.get_status()
    old_git = _git_stub_in(jj_test_home.bin_dir, "2.39.5")

    readiness = jj_service.probe_jj_readiness()

    assert isinstance(status.jj_readiness, JjAvailable)
    assert readiness == JjUnsupportedGit(
        blocker=JjBlocker.UNSUPPORTED_GIT, path=str(old_git), version="2.39.5", minimum_version=JJ_MINIMUM_GIT_VERSION
    )


def _jj_release_tarball(version: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in (
            ("./jj", f'#!/bin/sh\necho "jj {version}-{uuid4().hex}"\n'.encode()),
            ("./LICENSE", b"license"),
            ("./README.md", b"readme"),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@pytest.fixture
def local_release_server(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """Serve a directory over HTTP on localhost, standing in for GitHub releases."""
    served_dir = tmp_path / "release"
    served_dir.mkdir()
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(served_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield served_dir, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join()
    server.server_close()


class _JjManagedToolFromLocalRelease(JjManagedTool):
    """jj's managed install, downloading from a local server instead of GitHub releases."""

    def __init__(self, distribution: ResolvedDistribution) -> None:
        self._distribution = distribution

    def resolve_distribution(self) -> ResolvedDistribution:
        return self._distribution


def _local_jj_release(local_release_server: tuple[Path, str]) -> ResolvedDistribution:
    served_dir, base_url = local_release_server
    asset = f"jj-v{JJ_PINNED_VERSION}-test.tar.gz"
    tarball = _jj_release_tarball(JJ_PINNED_VERSION)
    (served_dir / asset).write_bytes(tarball)
    return ResolvedDistribution(
        version=JJ_PINNED_VERSION,
        url=f"{base_url}/{asset}",
        checksum_sha256=hashlib.sha256(tarball).hexdigest(),
        size=None,
        archive="tarball",
        binary_subpath=JjManagedTool.binary_subpath,
    )


@pytest.mark.allow_dependency_downloads
def test_a_finished_managed_jj_install_tells_every_window_that_jj_is_managed(
    jj_test_home: _JjTestHome,
    jj_service: DependencyManagementService,
    local_release_server: tuple[Path, str],
) -> None:
    _configure_jj("MANAGED")
    assert jj_service.get_status().jj.installed is False
    window: Queue[DependenciesStatus] = Queue()
    jj_service.add_observer_queue(window)

    result = jj_service._install_managed_tool(_JjManagedToolFromLocalRelease(_local_jj_release(local_release_server)))
    status = window.get(timeout=10.0)
    while status.jj.source != BinarySource.MANAGED:
        status = window.get(timeout=10.0)
    jj_service._install_thread[Dependency.JJ].join(timeout=10.0)

    assert result.success is True, result.error
    assert status.jj.managed_version == JJ_PINNED_VERSION


@pytest.mark.allow_dependency_downloads
def test_managed_jj_install_stages_the_binary_where_managed_mode_resolves_it(
    jj_test_home: _JjTestHome,
    jj_service: DependencyManagementService,
    local_release_server: tuple[Path, str],
) -> None:
    served_dir, base_url = local_release_server
    asset = f"jj-v{JJ_PINNED_VERSION}-test.tar.gz"
    tarball = _jj_release_tarball(JJ_PINNED_VERSION)
    (served_dir / asset).write_bytes(tarball)
    _configure_jj("MANAGED")
    distribution = ResolvedDistribution(
        version=JJ_PINNED_VERSION,
        url=f"{base_url}/{asset}",
        checksum_sha256=hashlib.sha256(tarball).hexdigest(),
        size=None,
        archive="tarball",
        binary_subpath=JjManagedTool.binary_subpath,
    )

    result = jj_service._download_verify_stage(JjManagedTool(), None, distribution)

    expected_binary = jj_test_home.managed_jj_dir / f"version-{JJ_PINNED_VERSION}" / "jj"
    assert result.success is True, result.error
    assert result.path == str(expected_binary)
    assert sorted(path.name for path in expected_binary.parent.iterdir()) == ["jj"]
    assert jj_service.resolve_binary_path(Dependency.JJ) == str(expected_binary)
    assert jj_service.get_status().jj.source == BinarySource.MANAGED
