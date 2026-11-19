"""Wrappers that record each run of a tool, for tests that count how often Sculptor runs one."""

import shlex
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG
from sculptor.utils.build import get_sculptor_folder


class RecordingBinaries(FrozenModel):
    """A directory of wrappers that each append a line to one log, then run the real tool with the same arguments."""

    bin_dir: Path
    log_path: Path

    def add(self, name: str, real_binary: Path) -> Path:
        """Put a wrapper named `name` for `real_binary` in `bin_dir`."""
        wrapper = self.bin_dir / name
        wrapper.write_text(
            "#!/bin/bash\n"
            + f'echo "{name} $*" >> {shlex.quote(str(self.log_path))}\n'
            + f'exec {shlex.quote(str(real_binary))} "$@"\n'
        )
        wrapper.chmod(0o755)
        return wrapper

    def read_runs(self) -> list[str]:
        """Each recorded run, as the tool's name and its arguments."""
        try:
            return self.log_path.read_text().splitlines()
        except FileNotFoundError:
            return []

    def forget_runs(self) -> None:
        self.log_path.write_text("")


@pytest.fixture
def recording_git_and_jj(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv
) -> Iterator[RecordingBinaries]:
    """Git and jj that record their runs as the only tools on PATH, in a fresh Sculptor folder.

    The user config resolves Claude and pi to nothing, and jj to the one on PATH, so
    computing the dependency status runs only these two.
    """
    real_git = shutil.which("git")
    assert real_git is not None
    bin_dir = tmp_path / "recording_bin"
    bin_dir.mkdir()
    recording = RecordingBinaries(bin_dir=bin_dir, log_path=tmp_path / "recorded_runs.log")
    recording.add("git", Path(real_git))
    recording.add("jj", jj_binary.path)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv(SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG, str(tmp_path / "recording_sculptor_folder"))
    get_sculptor_folder.cache_clear()
    set_user_config_instance(
        UserConfig(
            user_email="test@example.com",
            user_id=uuid4().hex,
            organization_id=uuid4().hex,
            instance_id=uuid4().hex,
            dependency_paths=DependencyPaths(claude="CUSTOM", pi="CUSTOM", jj="MANAGED"),
        )
    )
    yield recording
    set_user_config_instance(None)
    get_sculptor_folder.cache_clear()
