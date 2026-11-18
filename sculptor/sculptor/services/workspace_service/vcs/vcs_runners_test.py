from pathlib import Path
from uuid import uuid4

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners


def test_the_jj_runner_shares_the_binary_resolver_and_env_overrides_reader(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    fake_jj = tmp_path / "fake-jj"
    fake_jj.write_text('#!/bin/bash\necho "$SCULPTOR_TEST_MARKER"\n')
    fake_jj.chmod(0o755)
    marker = uuid4().hex
    runners = build_vcs_runners(
        test_root_concurrency_group,
        lambda tool: str(fake_jj) if tool is Dependency.JJ else None,
        lambda: {"SCULPTOR_TEST_MARKER": marker},
    )

    result = runners.jj.run(["status"], tmp_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)

    assert result.stdout.strip() == marker
