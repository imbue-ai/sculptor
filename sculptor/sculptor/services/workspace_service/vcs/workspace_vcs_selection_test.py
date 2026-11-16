import shutil
from pathlib import Path

import pytest

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.git_workspace_vcs import GitWorkspaceVcs
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import JjWorkspaceVcs
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners
from sculptor.services.workspace_service.vcs.workspace_vcs_selection import make_workspace_vcs
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import run_jj

_UNUSED_SNAPSHOT_LIMIT_MIB = 10


def _write_logging_git(directory: Path, invocation_log: Path) -> Path:
    real_git = shutil.which("git")
    assert real_git is not None
    wrapper = directory / "logging-git"
    wrapper.write_text(f'#!/bin/bash\necho "$*" >> "{invocation_log}"\nexec "{real_git}" "$@"\n')
    wrapper.chmod(0o755)
    return wrapper


@pytest.mark.parametrize(
    "strategy",
    [
        WorkspaceInitializationStrategy.IN_PLACE,
        WorkspaceInitializationStrategy.CLONE,
        WorkspaceInitializationStrategy.WORKTREE,
    ],
)
def test_git_workspace_kinds_get_git_version_control_that_runs_the_given_runner(
    strategy: WorkspaceInitializationStrategy,
    git_repo: Path,
    tmp_path: Path,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    invocation_log = tmp_path / "git-invocations.log"
    logging_git = _write_logging_git(tmp_path, invocation_log)
    runners = build_vcs_runners(
        test_root_concurrency_group, lambda tool: str(logging_git) if tool is Dependency.GIT else None
    )

    vcs = make_workspace_vcs(strategy, runners, test_root_concurrency_group, lambda: _UNUSED_SNAPSHOT_LIMIT_MIB)

    assert isinstance(vcs, GitWorkspaceVcs)
    assert vcs.list_target_candidates(git_repo) == ["main"]
    assert "branch" in invocation_log.read_text()


def test_built_runners_lay_the_env_overrides_over_every_git_command(
    git_repo: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    runners = build_vcs_runners(
        test_root_concurrency_group,
        lambda tool: shutil.which("git") if tool is Dependency.GIT else None,
        lambda: {"GIT_AUTHOR_NAME": "Override Author"},
    )

    result = runners.git.run_git(["var", "GIT_AUTHOR_IDENT"], git_repo, is_read_only=True)

    assert result.stdout.startswith("Override Author ")


def test_a_jj_workspace_gets_jj_version_control_that_reads_the_snapshot_limit_it_is_given(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_workspace: JjWorkspace,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    runners = build_vcs_runners(
        test_root_concurrency_group,
        lambda tool: str(jj_binary.path) if tool is Dependency.JJ else shutil.which("git"),
    )

    vcs = make_workspace_vcs(
        WorkspaceInitializationStrategy.JJ_WORKSPACE, runners, test_root_concurrency_group, lambda: 3
    )
    vcs.verify_checkout(
        CheckoutLocation(
            repo_path=jj_colocated_repo.path, checkout_path=jj_workspace.path, checkout_name=jj_workspace.name
        )
    )

    assert isinstance(vcs, JjWorkspaceVcs)
    configured = run_jj(jj_binary, ("config", "get", "snapshot.max-new-file-size"), cwd=jj_workspace.path)
    assert configured.strip() == str(3 * 1024 * 1024)
