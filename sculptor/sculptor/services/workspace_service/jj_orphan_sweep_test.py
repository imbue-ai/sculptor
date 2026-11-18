import shutil
from pathlib import Path

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.jj_orphan_sweep import forget_orphaned_jj_workspaces
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import run_jj


def _add_jj_workspace(jj_binary: JjBinary, repo: JjColocatedRepo, name: str, root: Path) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    run_jj(
        jj_binary,
        ("workspace", "add", "--no-colocate", "--name", name, "-r", repo.default_bookmark, str(root)),
        cwd=repo.path,
    )


def _list_jj_workspace_names(jj_binary: JjBinary, repo_path: Path) -> list[str]:
    return sorted(run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\\n"'), cwd=repo_path).split())


def test_only_a_sculptor_workspace_with_no_directory_and_no_live_owner_is_forgotten(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    jj = JjCli(test_root_concurrency_group, lambda tool: str(jj_binary.path) if tool is Dependency.JJ else None)
    orphan = str(WorkspaceID())
    live_without_directory = str(WorkspaceID())
    unowned_with_directory = str(WorkspaceID())
    users_own_without_directory = "scratch"
    environments = tmp_path / "environments"
    for name in (orphan, live_without_directory, unowned_with_directory, users_own_without_directory):
        _add_jj_workspace(jj_binary, jj_colocated_repo, name, environments / name / "code")
    for name in (orphan, live_without_directory, users_own_without_directory):
        shutil.rmtree(environments / name)

    forgotten = forget_orphaned_jj_workspaces(jj, jj_colocated_repo.path, live_workspace_ids={live_without_directory})

    assert forgotten == [orphan]
    assert _list_jj_workspace_names(jj_binary, jj_colocated_repo.path) == sorted(
        ["default", live_without_directory, unowned_with_directory, users_own_without_directory]
    )
