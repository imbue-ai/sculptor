from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.database.models import Project
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.jj_workspace_creation import JjWorkspaceCreationFacts
from sculptor.services.workspace_service.jj_workspace_creation import creates_jj_workspaces
from sculptor.services.workspace_service.jj_workspace_creation import gather_jj_workspace_creation_facts
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.testing.jj_readiness import BLOCKERS_THAT_LET_JJ_READ
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjReadiness

_JJ_AVAILABLE = JjAvailable(blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL))
_JJ_NOT_INSTALLED = JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED)


@pytest.fixture
def dependency_management_service() -> Iterator[DependencyManagementService]:
    with ConcurrencyGroup(name="dependency_management_service") as concurrency_group:
        yield DependencyManagementService(concurrency_group=concurrency_group)
    set_user_config_instance(None)


def _configure_jj(jj_value: str) -> None:
    set_user_config_instance(
        UserConfig(
            user_email="test@example.com",
            user_id=uuid4().hex,
            organization_id=uuid4().hex,
            instance_id=uuid4().hex,
            dependency_paths=DependencyPaths(jj=jj_value),
        )
    )


def _make_project(repo_path: Path, use_jj_for_new_workspaces: bool) -> Project:
    return Project(
        object_id=ProjectID(),
        organization_reference=OrganizationReference(uuid4().hex),
        name=repo_path.name,
        user_git_repo_url=f"file://{repo_path}",
        use_jj_for_new_workspaces=use_jj_for_new_workspaces,
    )


def _make_jj_cli(concurrency_group: ConcurrencyGroup, jj_binary_path: Path | None) -> JjCli:
    return JjCli(
        concurrency_group,
        lambda tool: str(jj_binary_path) if tool is Dependency.JJ and jj_binary_path is not None else None,
    )


def test_a_repository_creates_jj_workspaces_when_the_flag_is_on_it_is_colocated_and_jj_is_available() -> None:
    facts = JjWorkspaceCreationFacts(use_jj_for_new_workspaces=True, is_colocated=True, jj_readiness=_JJ_AVAILABLE)

    assert creates_jj_workspaces(facts) is True


@pytest.mark.parametrize(
    "facts",
    [
        JjWorkspaceCreationFacts(use_jj_for_new_workspaces=False, is_colocated=True, jj_readiness=_JJ_AVAILABLE),
        JjWorkspaceCreationFacts(use_jj_for_new_workspaces=True, is_colocated=False, jj_readiness=_JJ_AVAILABLE),
        JjWorkspaceCreationFacts(use_jj_for_new_workspaces=True, is_colocated=True, jj_readiness=_JJ_NOT_INSTALLED),
    ],
    ids=["flag_off", "not_colocated", "jj_unavailable"],
)
def test_a_repository_creates_git_workspaces_when_any_fact_is_missing(facts: JjWorkspaceCreationFacts) -> None:
    assert creates_jj_workspaces(facts) is False


def test_the_facts_of_a_colocated_repository_with_jj_available(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    test_root_concurrency_group: ConcurrencyGroup,
    dependency_management_service: DependencyManagementService,
) -> None:
    _configure_jj(str(jj_binary.path))
    project = _make_project(jj_colocated_repo.path, use_jj_for_new_workspaces=True)

    facts = gather_jj_workspace_creation_facts(
        project,
        _make_jj_cli(test_root_concurrency_group, jj_binary.path),
        dependency_management_service.probe_jj_readiness(),
    )

    assert facts == JjWorkspaceCreationFacts(
        use_jj_for_new_workspaces=True, is_colocated=True, jj_readiness=_JJ_AVAILABLE
    )


def test_the_facts_take_the_flag_from_the_project(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    test_root_concurrency_group: ConcurrencyGroup,
    dependency_management_service: DependencyManagementService,
) -> None:
    _configure_jj(str(jj_binary.path))
    project = _make_project(jj_colocated_repo.path, use_jj_for_new_workspaces=False)

    facts = gather_jj_workspace_creation_facts(
        project,
        _make_jj_cli(test_root_concurrency_group, jj_binary.path),
        dependency_management_service.probe_jj_readiness(),
    )

    assert facts.use_jj_for_new_workspaces is False


def test_a_plain_git_repository_is_not_colocated(
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
    test_root_concurrency_group: ConcurrencyGroup,
    dependency_management_service: DependencyManagementService,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    run_blocking(["git", "init", "-q"], cwd=repo_path)
    _configure_jj(str(jj_binary.path))
    project = _make_project(repo_path, use_jj_for_new_workspaces=True)

    facts = gather_jj_workspace_creation_facts(
        project,
        _make_jj_cli(test_root_concurrency_group, jj_binary.path),
        dependency_management_service.probe_jj_readiness(),
    )

    assert facts.is_colocated is False
    assert facts.jj_readiness == _JJ_AVAILABLE


@pytest.mark.parametrize("readiness", BLOCKERS_THAT_LET_JJ_READ)
def test_colocation_is_read_while_jj_is_unavailable_but_can_still_read_and_creates_no_jj_workspaces(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    test_root_concurrency_group: ConcurrencyGroup,
    readiness: JjReadiness,
) -> None:
    project = _make_project(jj_colocated_repo.path, use_jj_for_new_workspaces=True)

    facts = gather_jj_workspace_creation_facts(
        project, _make_jj_cli(test_root_concurrency_group, jj_binary.path), readiness
    )

    assert facts.is_colocated is True
    assert creates_jj_workspaces(facts) is False


def test_colocation_is_not_checked_while_jj_is_unavailable(
    jj_colocated_repo: JjColocatedRepo,
    test_root_concurrency_group: ConcurrencyGroup,
    dependency_management_service: DependencyManagementService,
) -> None:
    _configure_jj("CUSTOM")
    project = _make_project(jj_colocated_repo.path, use_jj_for_new_workspaces=True)

    # A runner that cannot find jj raises if it is ever asked to run.
    facts = gather_jj_workspace_creation_facts(
        project, _make_jj_cli(test_root_concurrency_group, None), dependency_management_service.probe_jj_readiness()
    )

    assert facts == JjWorkspaceCreationFacts(
        use_jj_for_new_workspaces=True, is_colocated=False, jj_readiness=_JJ_NOT_INSTALLED
    )
