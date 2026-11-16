from pathlib import Path

import pytest

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import run_jj
from sculptor.testing.server_utils import get_v1_frontend_path


def test_frontend_path_from_a_jj_workspace_nested_in_another_checkout_is_in_the_jj_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    enclosing_checkout = tmp_path / "enclosing_checkout"
    enclosing_checkout.mkdir()
    run_blocking(["git", "init", "-q"], cwd=enclosing_checkout)
    jj_workspace = enclosing_checkout / ".dev_sculptor" / "workspaces" / "ws" / "code"
    jj_workspace.parent.mkdir(parents=True)
    run_jj(
        jj_binary,
        ("workspace", "add", "--no-colocate", "--name", "ws", "-r", "main@origin", str(jj_workspace)),
        cwd=jj_colocated_repo.path,
    )
    (jj_workspace / "sculptor").mkdir()
    monkeypatch.chdir(jj_workspace / "sculptor")

    assert get_v1_frontend_path() == jj_workspace / "sculptor" / "frontend"
