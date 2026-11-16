from contextlib import contextmanager
from functools import partial
from typing import Generator

from sculptor.config.settings import SculptorSettings
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.btw_service.api import BtwService
from sculptor.services.ci_babysitter_service.coordinator import CIBabysitterCoordinator
from sculptor.services.jj_availability import find_ready_jj_binary
from sculptor.services.pi_login_service import PiLoginService
from sculptor.services.project_jj_state_service.project_jj_state_service import ProjectJjStateService
from sculptor.services.task_service.data_types import TaskServiceCollection
from sculptor.services.task_service.service_collection import get_task_service_collection
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners
from sculptor.web.pr_polling_service import PrPollingService


class CompleteServiceCollection(TaskServiceCollection):
    pr_polling_service: PrPollingService
    btw_service: BtwService
    ci_babysitter_service: CIBabysitterCoordinator
    pi_login_service: PiLoginService
    project_jj_state_service: ProjectJjStateService

    @contextmanager
    def run_all(self) -> Generator[None, None, None]:
        # The order is important here - it reflects the dependencies between services.
        # WorkspaceService manages EnvironmentManager internally.
        with (
            self.data_model_service.run(should_log_runtimes=True),
            self.dependency_management_service.run(should_log_runtimes=True),
            self.project_service.run(should_log_runtimes=True),
            self.project_jj_state_service.run(should_log_runtimes=True),
            self.workspace_service.run(should_log_runtimes=True),
            self.git_repo_service.run(should_log_runtimes=True),
            self.task_service.run(should_log_runtimes=True),
            self.pr_polling_service.run(should_log_runtimes=True),
            self.ci_babysitter_service.run(should_log_runtimes=True),
            self.btw_service.run(should_log_runtimes=True),
            self.pi_login_service.run(should_log_runtimes=True),
        ):
            yield


def get_services(
    concurrency_group: ConcurrencyGroup,
    settings: SculptorSettings,
) -> CompleteServiceCollection:
    services = get_task_service_collection(concurrency_group, settings)
    pr_polling_concurrency_group = concurrency_group.make_concurrency_group("pr_polling")
    pr_polling_service = PrPollingService(
        concurrency_group=pr_polling_concurrency_group,
        data_model_service=services.data_model_service,
        workspace_service=services.workspace_service,
        vcs_runners=build_vcs_runners(
            pr_polling_concurrency_group, services.dependency_management_service.resolve_binary_path
        ),
        read_ready_jj_binary=partial(find_ready_jj_binary, services.dependency_management_service),
    )
    btw_service = BtwService(concurrency_group=concurrency_group.make_concurrency_group("btw_service"))
    pi_login_service = PiLoginService(
        concurrency_group=concurrency_group.make_concurrency_group("pi_login_service"),
        data_model_service=services.data_model_service,
        task_service=services.task_service,
    )
    ci_babysitter_service = CIBabysitterCoordinator(
        concurrency_group=concurrency_group.make_concurrency_group("ci_babysitter"),
        data_model_service=services.data_model_service,
        task_service=services.task_service,
        git_repo_service=services.git_repo_service,
        pr_polling_service=pr_polling_service,
    )
    project_jj_state_concurrency_group = concurrency_group.make_concurrency_group("project_jj_state")
    project_jj_state_service = ProjectJjStateService(
        concurrency_group=project_jj_state_concurrency_group,
        data_model_service=services.data_model_service,
        project_service=services.project_service,
        dependency_management_service=services.dependency_management_service,
        vcs_runners=build_vcs_runners(
            project_jj_state_concurrency_group, services.dependency_management_service.resolve_binary_path
        ),
    )
    return CompleteServiceCollection(
        settings=settings,
        data_model_service=services.data_model_service,
        dependency_management_service=services.dependency_management_service,
        task_service=services.task_service,
        git_repo_service=services.git_repo_service,
        project_service=services.project_service,
        workspace_service=services.workspace_service,
        pr_polling_service=pr_polling_service,
        btw_service=btw_service,
        ci_babysitter_service=ci_babysitter_service,
        pi_login_service=pi_login_service,
        project_jj_state_service=project_jj_state_service,
    )
