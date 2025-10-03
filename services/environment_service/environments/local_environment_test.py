import shutil
import time
from typing import Generator
from uuid import uuid4

import pytest

from imbue_core.agents.data_types.ids import ProjectID
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.environment_service.providers.local.constants import LOCAL_SANDBOX_DIR


@pytest.fixture
def local_environment() -> Generator[LocalEnvironment, None, None]:
    sandbox_dir = LOCAL_SANDBOX_DIR / str(uuid4().hex)
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    try:
        environment_config = LocalEnvironmentConfig()
        local_env = LocalEnvironment(
            config=environment_config, environment_id=LocalEnvironmentID(str(sandbox_dir)), project_id=ProjectID()
        )
        local_env.to_host_path(local_env.get_workspace_path()).mkdir(parents=True, exist_ok=True)
        yield local_env
    finally:
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def test_processes_are_closed_on_exit(local_environment: LocalEnvironment):
    proc = local_environment.run_process_in_background(["sleep", "60"], {})
    assert len(local_environment._processes) == 1
    # you MUST do this right now -- give it a few seconds to start
    # otherwise the test is flaky because the process might not have started before we call close below
    time.sleep(5.0)
    assert proc.poll() is None
    local_environment.close()
    assert proc.poll() is not None
