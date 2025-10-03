from __future__ import annotations

import subprocess
from contextlib import contextmanager
from typing import Generator

from loguru import logger
from tenacity import retry
from tenacity import retry_all
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.errors import ExpectedError
from imbue_core.itertools import only
from sculptor.database.core import create_new_engine
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.utils import convert_sqlite_url_to_read_only_format
from sculptor.interfaces.environments.v1.base import LocalDockerEnvironmentConfig
from sculptor.primitives.ids import DockerContainerID
from sculptor.services.data_model_service.sql_implementation import SQLDataModelService
from sculptor.services.environment_service.environments.docker_environment import DockerEnvironment


class MissingContainerError(ExpectedError):
    pass


retry_find_containers = retry(
    stop=stop_after_attempt(8),
    wait=wait_exponential(min=2.0, max=40, exp_base=2),
    retry=retry_all(retry_if_exception_type((MissingContainerError,))),
)


def _get_container_id_for_task(task_id: str) -> str:
    result = subprocess.run(
        ["bash", "-c", f"docker ps --format '{{{{.ID}}}} {{{{.Names}}}}' | grep {task_id}"],
        check=True,
        capture_output=True,
        text=True,
    )
    container_lines = result.stdout.strip().splitlines()
    containers = [(line.split(maxsplit=1)[0], line.split(maxsplit=1)[1]) for line in container_lines if line.strip()]
    return only(containers)[0]


@contextmanager
def with_mock_claude_output(
    task_id: str, project_id: ProjectID, output_contents: str, exit_code: int = 0
) -> Generator[None, None, None]:
    container_id = _get_container_id_for_task(task_id)
    environment = DockerEnvironment(
        config=LocalDockerEnvironmentConfig(server_port_by_name={}),
        environment_id=DockerContainerID(container_id),
        server_port_by_name={},
        project_id=project_id,
    )
    # TODO: See if there's a way to inject a fake claude binary into the container.
    # See: https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5565#note_2718971649
    claude_path_filename = "/imbue_addons/agent_path_extension_bin/claude"
    tmp_claude = "/tmp/claude_copy"
    content_filename = f"/tmp/claude_output_{task_id}"
    try:
        environment.write_file(content_filename, output_contents)
        environment.move_file(claude_path_filename, tmp_claude, run_as_root=True)
        environment.write_file(
            claude_path_filename, f"#!/bin/bash\ncat {content_filename}\nexit {exit_code}", run_as_root=True
        )
        environment.run_process_to_completion(
            command=["chmod", "+x", claude_path_filename],
            secrets={},
            run_as_root=True,
        )
        yield
    finally:
        if environment.is_alive():
            try:
                environment.move_file(tmp_claude, claude_path_filename, run_as_root=True)
            except FileNotFoundError:
                logger.debug("Didn't find claude at tmp location to move back, proceeding")
            environment.run_process_in_background(
                command=["rm", "-f", content_filename],
                secrets={},
            )


@retry_find_containers
def get_containers_with_tasks(database_url: str) -> tuple[tuple[str, str], ...]:
    data_model_service = SQLDataModelService()
    database_url_read_only = convert_sqlite_url_to_read_only_format(database_url)
    data_model_service._engine = create_new_engine(database_url_read_only)
    data_model_service._is_read_only = True
    data_model_service.start()
    with data_model_service.open_task_transaction() as transaction:
        tasks = transaction.get_all_tasks()

    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.ID}} {{.Names}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    container_lines = result.stdout.strip().splitlines()
    containers = [(line.split(maxsplit=1)[0], line.split(maxsplit=1)[1]) for line in container_lines if line.strip()]

    containers_with_tasks = []

    for task in tasks:
        if not isinstance(task.input_data, AgentTaskInputsV1):
            continue
        task_id = task.object_id

        candidates = [container_id for container_id, name in containers if str(task_id) in name]
        if len(candidates) != 1:
            error_message = f"Expected exactly one container for task {task_id}, found {len(candidates)}"
            raise MissingContainerError(error_message)
            # if fail_if_missing:
            #     raise ValueError(error_message)
            #
            # logger.info("{}. Skipping task {}.", error_message, task_id)
            # continue

        matched_container_id = only(candidates)
        containers_with_tasks.append((matched_container_id, task_id))

    return tuple(containers_with_tasks)
