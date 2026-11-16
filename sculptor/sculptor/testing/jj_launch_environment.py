"""A pytest fixture for tests of processes Sculptor launches in a jj workspace.

The backend has no jj on its PATH and resolves jj only through a managed copy
staged in the test's own Sculptor folder, so a process that finds jj found it
through what Sculptor put on its PATH. HOME is a fresh directory, so a login
shell reads no developer profile that puts another jj on PATH. The workspace's
environment directory sits inside a git repository, as workspaces do when
Sculptor runs from source.

A test module requesting the fixture also imports `isolated_sculptor_folder`
from `sculptor.testing.sculptor_folder`, which it depends on.
"""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ConfigDict

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.workspace_vcs import make_test_jj_workspace_vcs

# Directories that hold no jj on any machine the tests run on.
_SYSTEM_PATH_WITHOUT_JJ = ("/usr/bin", "/bin")


class JjLaunchEnvironment(FrozenModel):
    """A jj workspace's environment, its version control, and where its checkout is."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    environment: LocalEnvironment
    vcs: WorkspaceVcs
    location: CheckoutLocation
    managed_jj: Path
    enclosing_git_repository: Path


@pytest.fixture
def jj_environment_nested_in_git_repository(
    isolated_sculptor_folder: Path,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_root_concurrency_group: ConcurrencyGroup,
) -> Iterator[JjLaunchEnvironment]:
    git_binary = shutil.which("git")
    assert git_binary is not None
    git_only_bin = tmp_path / "git_only_bin"
    git_only_bin.mkdir()
    (git_only_bin / "git").symlink_to(git_binary)
    monkeypatch.setenv("PATH", os.pathsep.join([str(git_only_bin), *_SYSTEM_PATH_WITHOUT_JJ]))
    home_without_profile = tmp_path / "home"
    home_without_profile.mkdir()
    monkeypatch.setenv("HOME", str(home_without_profile))
    assert shutil.which("jj") is None
    managed_jj = isolated_sculptor_folder / "internal" / "dependencies" / "jj" / f"version-{JJ_PINNED_VERSION}" / "jj"
    managed_jj.parent.mkdir(parents=True)
    managed_jj.symlink_to(jj_binary.path)
    enclosing_git_repository = tmp_path / "enclosing_git_repository"
    enclosing_git_repository.mkdir()
    run_blocking(["git", "init", "-q"], cwd=enclosing_git_repository)

    set_user_config_instance(
        UserConfig(
            user_email="test@example.com",
            user_id=uuid4().hex,
            organization_id=uuid4().hex,
            instance_id=uuid4().hex,
            dependency_paths=DependencyPaths(jj="MANAGED"),
        )
    )
    try:
        vcs = make_test_jj_workspace_vcs(test_root_concurrency_group)
        workspace_id = WorkspaceID()
        environment = LocalEnvironment.create(
            environment_id=LocalEnvironmentID(str(enclosing_git_repository / "environment")),
            project_id=ProjectID(),
            concurrency_group=test_root_concurrency_group,
            repo_host_path=jj_colocated_repo.path,
            vcs=vcs,
            workspace_id=workspace_id,
            initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE,
            source_branch=f"{jj_colocated_repo.default_bookmark}@origin",
        )
        try:
            yield JjLaunchEnvironment(
                environment=environment,
                vcs=vcs,
                location=CheckoutLocation(
                    repo_path=jj_colocated_repo.path,
                    checkout_path=environment.get_working_directory(),
                    checkout_name=str(workspace_id),
                ),
                managed_jj=managed_jj,
                enclosing_git_repository=enclosing_git_repository,
            )
        finally:
            environment.close()
    finally:
        set_user_config_instance(None)
