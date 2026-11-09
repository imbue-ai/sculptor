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
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity


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
    assert status.jj_readiness.blocker == JjBlocker.NOT_INSTALLED


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
    assert status.jj_readiness.blocker is None
    assert status.jj_readiness.identity == JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)


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
    assert status.jj_readiness.blocker is None


def test_jj_custom_path_resolves_the_configured_binary(
    jj_test_home: _JjTestHome, jj_binary: JjBinary, jj_service: DependencyManagementService
) -> None:
    _configure_jj(str(jj_binary.path))

    status = jj_service.get_status()

    assert status.jj.path == str(jj_binary.path)
    assert status.jj.mode == BinaryMode.CUSTOM
    assert status.jj.source == BinarySource.EXTERNAL
    assert status.jj_readiness.blocker is None


def test_jj_that_fails_to_run_is_not_runnable_with_the_first_stderr_line(
    jj_test_home: _JjTestHome,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    jj_service: DependencyManagementService,
) -> None:
    jj_isolated_env.jj_config_path.write_text("garbage = =\n")
    _configure_jj(str(jj_binary.path))

    readiness = jj_service.get_jj_readiness()

    assert readiness.blocker == JjBlocker.NOT_RUNNABLE
    assert readiness.detail == "Config error: Configuration cannot be parsed as TOML document"


def test_an_old_jj_is_unsupported_and_reports_its_path_and_version(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    stub = _old_jj_stub(jj_test_home)
    _configure_jj("MANAGED")

    status = jj_service.get_status()

    assert status.jj.is_version_in_range is False
    assert status.jj_readiness.blocker == JjBlocker.UNSUPPORTED_VERSION
    assert status.jj_readiness.detail == f"{stub} reports jj 0.45.0"


def test_a_jj_with_unrecognized_version_output_is_unsupported(
    jj_test_home: _JjTestHome, jj_service: DependencyManagementService
) -> None:
    stub = jj_test_home.write_stub("jj", 'echo "jujutsu nightly"')
    _configure_jj("MANAGED")

    readiness = jj_service.get_jj_readiness()

    assert readiness.blocker == JjBlocker.UNSUPPORTED_VERSION
    assert readiness.detail == f"{stub} reports no recognizable jj version"


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

    assert readiness.blocker == JjBlocker.NO_IDENTITY
    assert readiness.identity is None
    assert readiness.suggested_identity == JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)


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

    assert readiness.blocker == JjBlocker.NO_IDENTITY
    assert readiness.suggested_identity == JjIdentity(name="Ada Lovelace", email=JJ_TEST_USER_EMAIL)


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

    assert readiness.blocker is None
    assert readiness.identity == JjIdentity(name="Env File User", email="env-file@example.com")


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

    assert status.jj_readiness.blocker is None
    assert status.jj_readiness.identity == identity
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
