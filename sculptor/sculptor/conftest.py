from typing import Generator
from typing import cast

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.user_config import UserConfig
from sculptor.config.settings import SculptorSettings
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.btw_service.api import BtwService
from sculptor.services.ci_babysitter_service.coordinator import CIBabysitterCoordinator
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.dependency_management_service import InstallResult
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.default_implementation import DefaultGitRepoService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.project_service.default_implementation import DefaultProjectService
from sculptor.services.task_service.api import TaskService
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService
from sculptor.services.user_config.user_config import get_default_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.web.pr_polling_service import PrPollingService


@pytest.fixture
def silly_global_config() -> Generator[UserConfig, None, None]:
    config = get_default_user_config_instance()
    set_user_config_instance(config)
    yield config
    set_user_config_instance(None)


# NOTE: We use the leading underscore notation to highlight the fact that services should not be used on their own outside of this module.
# (They need to be started and stopped in a controlled manner so always require the whole collection instead of individual services.)


@pytest.fixture
def _test_data_model_service(
    test_settings: SculptorSettings, test_root_concurrency_group: ConcurrencyGroup
) -> DataModelService:
    return SQLDataModelService.build_from_settings(
        test_settings, test_root_concurrency_group.make_concurrency_group("data_model_service")
    )


@pytest.fixture
def _test_git_repo_service(test_root_concurrency_group: ConcurrencyGroup) -> GitRepoService:
    return DefaultGitRepoService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("git_repo_service")
    )


@pytest.fixture
def _test_project_service(
    _test_data_model_service: DataModelService,
    test_root_concurrency_group: ConcurrencyGroup,
) -> ProjectService:
    return DefaultProjectService(
        data_model_service=_test_data_model_service,
        concurrency_group=test_root_concurrency_group.make_concurrency_group("project_service"),
    )


@pytest.fixture
def _test_dependency_management_service(
    test_root_concurrency_group: ConcurrencyGroup,
) -> DependencyManagementService:
    return DependencyManagementService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("dependency_management_service"),
    )


@pytest.fixture
def _test_workspace_service(
    _test_data_model_service: DataModelService,
    _test_dependency_management_service: DependencyManagementService,
    _test_git_repo_service: GitRepoService,
    _test_project_service: ProjectService,
    test_root_concurrency_group: ConcurrencyGroup,
    test_settings: SculptorSettings,
) -> WorkspaceService:
    return DefaultWorkspaceService.build(
        concurrency_group=test_root_concurrency_group,
        settings=test_settings,
        data_model_service=_test_data_model_service,
        dependency_management_service=_test_dependency_management_service,
        project_service=_test_project_service,
    )


@pytest.fixture
def _test_task_service(
    test_root_concurrency_group: ConcurrencyGroup,
    test_settings: SculptorSettings,
    _test_data_model_service: DataModelService,
    _test_dependency_management_service: DependencyManagementService,
    _test_git_repo_service: GitRepoService,
    _test_project_service: ProjectService,
    _test_workspace_service: WorkspaceService,
) -> TaskService:
    return LocalThreadTaskService(
        settings=test_settings,
        data_model_service=cast(TaskDataModelService, _test_data_model_service),
        dependency_management_service=_test_dependency_management_service,
        git_repo_service=_test_git_repo_service,
        project_service=_test_project_service,
        workspace_service=_test_workspace_service,
        concurrency_group=test_root_concurrency_group.make_concurrency_group("task_service"),
        task_sync_dir=test_settings.task_sync_path,
    )


@pytest.fixture
def test_service_collection(
    test_settings: SculptorSettings,
    test_root_concurrency_group: ConcurrencyGroup,
    silly_global_config: UserConfig,  # noqa: F811
    _test_data_model_service: DataModelService,
    _test_dependency_management_service: DependencyManagementService,
    _test_git_repo_service: GitRepoService,
    _test_task_service: TaskService,
    _test_project_service: ProjectService,
    _test_workspace_service: WorkspaceService,
) -> Generator[CompleteServiceCollection, None, None]:
    pr_polling_service = PrPollingService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("pr_polling"),
        data_model_service=_test_data_model_service,
        workspace_service=_test_workspace_service,
    )
    ci_babysitter_service = CIBabysitterCoordinator(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("ci_babysitter"),
        data_model_service=_test_data_model_service,
        task_service=_test_task_service,
        git_repo_service=_test_git_repo_service,
        pr_polling_service=pr_polling_service,
    )
    services = CompleteServiceCollection(
        settings=test_settings,
        data_model_service=_test_data_model_service,
        dependency_management_service=_test_dependency_management_service,
        task_service=_test_task_service,
        git_repo_service=_test_git_repo_service,
        project_service=_test_project_service,
        workspace_service=_test_workspace_service,
        pr_polling_service=pr_polling_service,
        btw_service=BtwService(concurrency_group=test_root_concurrency_group.make_concurrency_group("btw_service")),
        ci_babysitter_service=ci_babysitter_service,
    )
    with services.run_all():
        yield services


def _noop_auto_install(_self: DependencyManagementService) -> None:
    """Stand-in for ``_auto_install_if_needed``: unit tests never auto-provision binaries."""
    return None


def _raise_on_managed_download(_self: DependencyManagementService, *_args: object, **_kwargs: object) -> InstallResult:
    """Stand-in for the managed install/download methods: a unit test must never reach the network."""
    raise AssertionError(
        "A unit test tried to download a managed binary. Mock the download, or mark the test "
        + "@pytest.mark.allow_dependency_downloads if it exercises the install path with the network stubbed."
    )


@pytest.fixture(autouse=True)
def _block_managed_binary_downloads(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never download a managed binary from a remote source.

    Both Claude and pi default to MANAGED, so standing up the service collection
    (``test_service_collection``) would otherwise have the dependency-management
    service auto-provision them from their upstream release sources on startup — on
    every test, on every CI run where nothing is pre-staged. This mocks the download
    manager out: startup auto-install becomes a no-op, and any attempt to start a
    managed install raises instead of reaching the network, so an accidental download
    fails fast rather than silently slowing the suite.

    Tests that drive the real install/download flow with the network stubbed
    themselves opt out with ``@pytest.mark.allow_dependency_downloads``.
    """
    if request.node.get_closest_marker("allow_dependency_downloads"):
        return

    # Block every network-touching entry point: startup auto-install becomes a no-op,
    # and both the install kickoff and the download/verify/stage core raise on contact.
    monkeypatch.setattr(DependencyManagementService, "_auto_install_if_needed", _noop_auto_install)
    monkeypatch.setattr(DependencyManagementService, "_install_managed_tool", _raise_on_managed_download)
    monkeypatch.setattr(DependencyManagementService, "_download_verify_stage", _raise_on_managed_download)
