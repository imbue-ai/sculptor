from pathlib import Path
from typing import Generator

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.vcs.git_cli import GitCli


@pytest.fixture(autouse=True)
def hermetic_git_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's own git config (signing, hooks, default branch) out of every test."""
    global_config = tmp_path / "gitconfig"
    global_config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture(autouse=True)
def reset_user_config() -> Generator[None, None, None]:
    """Drop any user config a test installed, such as one pointing `dependency_paths` at a fake binary."""
    yield
    set_user_config_instance(None)


@pytest.fixture
def git_cli(test_root_concurrency_group: ConcurrencyGroup) -> GitCli:
    dependency_management_service = DependencyManagementService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("dependency_management_service"),
    )
    return GitCli(test_root_concurrency_group, dependency_management_service)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repository on `main` with one commit holding `file.txt`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_blocking(["git", "init", "-q", "-b", "main"], cwd=repo)
    (repo / "file.txt").write_text("content\n")
    run_blocking(["git", "add", "file.txt"], cwd=repo)
    run_blocking(["git", "commit", "-q", "-m", "init"], cwd=repo)
    return repo
